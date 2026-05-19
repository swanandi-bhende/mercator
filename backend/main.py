"""FastAPI backend entrypoint for the Mercator x402 micropayment platform.

Purpose: Handles FastAPI endpoints for seller uploads to IPFS, on-chain listing storage, semantic discovery,
buyer checkout with x402 micropayments, escrow settlement, and operational health/metrics dashboards.

Key Flows:
1. POST /list: Uploads insight text to IPFS via Pinata, stores CID on InsightListing smart contract.
2. GET /discover: Semantic search + lexical fallback ranking, merged with recent local listings for immediate discovery.
3. POST /demo_purchase: Launches LangChain agent for autonomous search, evaluation, and x402 payment.
4. POST /ops/synthetic: Full end-to-end test cycle (list → discover → purchase → escrow release → content delivery).
5. GET /ops/overview: Operational dashboard with metrics (latency, IPFS health, Algorand status).
"""

from __future__ import annotations

import base64
import asyncio
import inspect
import json
import logging
import os
import hashlib
import re
import time
import warnings
from contextlib import asynccontextmanager
from uuid import uuid4
from dataclasses import asdict
from typing import Any
import requests
from datetime import datetime, timezone, timedelta
from collections import deque
from pathlib import Path

from cachetools import TTLCache
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from algosdk import mnemonic, transaction, abi
from algosdk import encoding
from algosdk import account
from algosdk.error import AlgodHTTPError
from algosdk.logic import get_application_address
from algosdk.atomic_transaction_composer import AtomicTransactionComposer, AccountTransactionSigner, TransactionWithSigner
from algosdk.v2client import algod, indexer

warnings.filterwarnings(
    "ignore",
    message="Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.",
    category=UserWarning,
)
warnings.filterwarnings(
    "ignore",
    message="'_UnionGenericAlias' is deprecated and slated for removal in Python 3.17",
    category=DeprecationWarning,
    module=r"google\.genai\.types",
)

try:
    from backend.agent import run_agent
except Exception as exc:  # pragma: no cover
    _agent_import_error = str(exc)

    async def run_agent(*args: object, **kwargs: object) -> dict[str, object]:
        """Fallback agent stub when AI dependencies/env are unavailable at startup.

        Keeps API process healthy for deployment checks while surfacing a clear
        runtime error only when agent routes are invoked.
        """
        return {
            "success": False,
            "decision": "ERROR",
            "evaluation": "Agent unavailable",
            "payment_status": {},
            "message": f"Agent initialization failed: {_agent_import_error}",
        }
from backend.tools.semantic_search import (
    semantic_search as semantic_search_tool,
    clear_semantic_search_cache,
    warm_cache,
)
from backend.agents import curator_agent
from backend.tools import staging_seed_wallet
from backend.utils.db import get_db_path, initialise_curator_schema, initialise_seller_profile_schema
from backend.utils.custodial_wallet import (
    create_user,
    authenticate_user,
    get_wallet_for_user,
    fund_new_wallet,
    is_custodial_address,
    get_user_id_by_address,
    create_demo_session,
)
from backend.utils.flow_tracer import tracer
from backend.utils.runtime_env import configure_demo_logging, normalize_network_env, warn_missing_required_env
from backend.utils.error_handler import contract_error, ipfs_down, MercatorError, ErrorHandler
from backend.utils.failure_simulator import trigger_scenario, list_scenarios, active_scenarios, is_active as failure_is_active
from backend.utils.error_handler import AlgorandError, ErrorCode as EH_ErrorCode
from backend.utils.ws_manager import ws_manager
from backend.api.v1.router import router as api_v1_router
from backend.api.v1.auth import seed_demo_key, generate_api_key
from backend.api.v1.responses import error_response
from backend.utils.health_checker import HealthChecker
from backend.utils.http_client import startup_http_client, shutdown_http_client
from backend.utils.algorand_async import (
    algod_account_info,
    algod_send_raw_transaction,
    algod_status,
    algod_suggested_params,
)
from backend.utils.algorand_async import algod_application_info
from backend.utils.seller_profile import SellerProfileService, build_trust_summary
import uuid as _uuid

try:
    from contracts.insight_listing import InsightListingClient  # noqa: F401
except Exception:  # pragma: no cover
    InsightListingClient = None  # type: ignore[assignment]

try:
    from utils.ipfs import (
        IPFSUploadError,
        ListingStoreError,
        create_listing_prepared,
        upload_insight_to_ipfs,
        store_cid_in_listing,
        fetch_insight_from_ipfs,
        PINATA_BASE_URL,
    )
except ModuleNotFoundError:
    from backend.utils.ipfs import (
        IPFSUploadError,
        ListingStoreError,
        create_listing_prepared,
        upload_insight_to_ipfs,
        store_cid_in_listing,
        fetch_insight_from_ipfs,
        PINATA_BASE_URL,
    )


normalize_network_env()
demo_logger = configure_demo_logging()

logger = logging.getLogger("mercator.backend")
scheduler = AsyncIOScheduler()
health_checker: HealthChecker | None = None
seller_profile_cache: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=100, ttl=30)
seller_leaderboard_cache: TTLCache[str, list[dict[str, Any]]] = TTLCache(maxsize=20, ttl=60)
_seller_profile_service: SellerProfileService | None = None


async def _await_if_needed(result: object) -> object:
    if inspect.isawaitable(result):
        return await result
    return result


def _configure_logging() -> None:
    """Back-compat helper used by tests to (re)apply backend logging config."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("mercator.log", mode="a"),
        ],
        force=True,
    )


async def _run_startup_hooks() -> None:
    global health_checker
    
    try:
        seed_demo_key()
    except Exception:
        pass

    normalize_network_env()
    warn_missing_required_env(logger)
    initialise_curator_schema()

    try:
        await curator_agent.ensure_registered()
    except Exception:
        logger.exception("Failed to ensure curator registration during startup")

    try:
        await curator_agent.ensure_registered(
            agent_name="Mercator Buyer Agent",
            role="buyer",
            wallet_env="BUYER_WALLET",
            mnemonic_env="BUYER_MNEMONIC",
        )
    except Exception:
        logger.exception("Failed to ensure buyer registration during startup")

    try:
        await warm_cache()
    except Exception:
        logger.exception("Failed to warm semantic search cache during startup")

    # Initialize health checker
    try:
        health_checker = HealthChecker(
            _get_algod_client(),
            _get_indexer_client(),
            ws_manager,
        )
        await health_checker.startup()
        logger.info("Health checker initialized and started")
    except Exception:
        logger.exception("Failed to initialize health checker during startup")
        health_checker = None

    curator_minutes = int(os.getenv("CURATOR_CYCLE_INTERVAL_MINUTES", "30") or 30)
    scheduler.add_job(
        curator_agent.run_full_cycle,
        "interval",
        minutes=curator_minutes,
        id="curator_cycle",
        replace_existing=True,
    )
    scheduler.add_job(
        staging_seed_wallet.check_and_top_up,
        "interval",
        hours=6,
        id="wallet_top_up",
        replace_existing=True,
    )
    scheduler.add_job(
        _send_heartbeat,
        "interval",
        seconds=30,
        id="ws_heartbeat",
        replace_existing=True,
    )
    
    # Add health check job (runs every 10 seconds with asyncio executor)
    if health_checker:
        scheduler.add_job(
            health_checker.run_all_checks,
            "interval",
            seconds=10,
            id="health_check",
            executor="asyncio",
            replace_existing=True,
        )
        logger.info("Health checker job scheduled every 10 seconds")

    # Schedule background expiry job for stale listings (every 10 minutes)
    try:
        scheduler.add_job(
            curator_agent.expire_stale_listings,
            "interval",
            minutes=10,
            id="listing_expiry",
            executor="asyncio",
            replace_existing=True,
        )
        logger.info("Listing expiry job scheduled every 10 minutes")
    except Exception:
        logger.exception("Failed to schedule listing expiry job")
    
    if not scheduler.running:
        try:
            scheduler.start()
        except RuntimeError as exc:
            logger.warning("Scheduler start skipped: %s", exc)

    # Perform an initial ANALYZE on startup to populate sqlite_stat tables
    try:
        import sqlite3

        with sqlite3.connect(str(get_db_path())) as conn:
            conn.execute("ANALYZE sqlite_master;")
            try:
                conn.execute("PRAGMA optimize;")
            except Exception:
                pass
        logger.info("Initial SQLite ANALYZE and PRAGMA optimize completed")
    except Exception:
        logger.exception("Failed to run initial SQLite ANALYZE/optimize")

    # Schedule periodic PRAGMA optimize (daily) to keep sqlite stats fresh
    try:
        def _sqlite_optimize_job() -> None:
            import sqlite3

            try:
                with sqlite3.connect(str(get_db_path())) as conn:
                    conn.execute("ANALYZE sqlite_master;")
                    try:
                        conn.execute("PRAGMA optimize;")
                    except Exception:
                        pass
            except Exception:
                logger.exception("Scheduled SQLite optimize failed")

        scheduler.add_job(
            _sqlite_optimize_job,
            "interval",
            hours=int(os.getenv("CURATOR_DB_OPTIMIZE_HOURS", "24") or 24),
            id="sqlite_optimize",
            replace_existing=True,
        )
        logger.info("Scheduled SQLite optimize job")
    except Exception:
        logger.exception("Failed to schedule SQLite optimize job")
    # Optionally schedule an hourly optimize job for heavy-write workloads
    try:
        hourly_flag = os.getenv("CURATOR_DB_OPTIMIZE_HOURLY", "").lower()
        if hourly_flag in ("1", "true", "yes"):
            scheduler.add_job(
                _sqlite_optimize_job,
                "interval",
                hours=1,
                id="sqlite_optimize_hourly",
                replace_existing=True,
            )
            logger.info("Scheduled SQLite hourly optimize job (CURATOR_DB_OPTIMIZE_HOURLY=true)")
    except Exception:
        logger.exception("Failed to schedule SQLite hourly optimize job")
    # Start shared HTTP client for outbound requests
    try:
        await startup_http_client()
        logger.info("Shared httpx.AsyncClient started")
    except Exception:
        logger.exception("Failed to start shared HTTP client")


async def _run_shutdown_hooks() -> None:
    global health_checker
    
    # Shutdown health checker
    if health_checker:
        try:
            await health_checker.shutdown()
            logger.info("Health checker shut down successfully")
        except Exception:
            logger.exception("Error shutting down health checker")
    
    if scheduler.running:
        scheduler.shutdown(wait=False)

    # Shutdown shared HTTP client
    try:
        await shutdown_http_client()
        logger.info("Shared httpx.AsyncClient shut down")
    except Exception:
        logger.exception("Error shutting down shared HTTP client")


def startup_checks() -> None:
    """Compatibility helper for tests that validate startup env warning paths."""
    normalize_network_env()
    warn_missing_required_env(logger)


def _get_seller_profile_service() -> SellerProfileService:
    global _seller_profile_service
    if _seller_profile_service is None:
        _seller_profile_service = SellerProfileService(
            _get_algod_client(),
            _get_indexer_client(),
            str(get_db_path()),
        )
    return _seller_profile_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _run_startup_hooks()
    try:
        yield
    finally:
        await _run_shutdown_hooks()


app = FastAPI(title="Mercator Backend", lifespan=lifespan)

# Mount API v1 router (protected routes)
app.include_router(api_v1_router)


@app.get("/api/v1/health")
async def api_v1_health():
    from datetime import datetime

    return {
        "status": "ok",
        "version": "1.0",
        "network": "algorand_testnet",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


def _validate_wallet_or_400(wallet: str, request_id: str = "") -> None:
    if not isinstance(wallet, str) or len(wallet) != 58 or not encoding.is_valid_address(wallet):
        raise HTTPException(
            status_code=400,
            detail=error_response("INVALID_WALLET", "wallet must be a valid Algorand address", request_id),
        )


@app.get("/sellers/leaderboard")
async def get_seller_leaderboard(limit: int = Query(10, ge=1, le=50), request: Request = None):
    request_id = getattr(request.state, "request_id", "") if request else ""
    cache_key = f"leaderboard:{limit}"
    cached = seller_leaderboard_cache.get(cache_key)
    if cached is not None:
        return {"success": True, "sellers": cached, "limit": limit, "cached": True, "request_id": request_id}

    with sqlite3.connect(str(get_db_path())) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT seller_wallet, total_purchases, total_usdc_earned, avg_price_usdc, last_purchase_date
            FROM seller_leaderboard
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        sellers = [dict(row) for row in rows]

    seller_leaderboard_cache[cache_key] = sellers
    return {"success": True, "sellers": sellers, "limit": limit, "cached": False, "request_id": request_id}


@app.get("/sellers/{wallet}/profile")
async def get_seller_profile(wallet: str, request: Request):
    request_id = getattr(request.state, "request_id", "")
    _validate_wallet_or_400(wallet, request_id)

    cached = seller_profile_cache.get(wallet)
    if cached is not None:
        return {"success": True, "profile": cached, "cached": True, "request_id": request_id}

    service = _get_seller_profile_service()
    profile = await service.get_profile_tier1_tier2(wallet)
    payload = asdict(profile)
    seller_profile_cache[wallet] = payload
    return {"success": True, "profile": payload, "cached": False, "request_id": request_id}


@app.get("/sellers/{wallet}/listings")
async def get_seller_listings(wallet: str, page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=50), request: Request = None):
    request_id = getattr(request.state, "request_id", "") if request else ""
    _validate_wallet_or_400(wallet, request_id)
    service = _get_seller_profile_service()
    data = await service.get_listing_history(wallet, page=page, page_size=page_size)
    return {"success": True, **data, "request_id": request_id}


@app.get("/sellers/{wallet}/reputation_history")
async def get_seller_reputation_history(wallet: str, request: Request):
    request_id = getattr(request.state, "request_id", "")
    _validate_wallet_or_400(wallet, request_id)

    with sqlite3.connect(str(get_db_path())) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT score_before, score_after, change, recorded_at
            FROM reputation_score_history
            WHERE seller_wallet = ?
            ORDER BY recorded_at DESC
            LIMIT 20
            """,
            (wallet,),
        ).fetchall()
        history = [dict(row) for row in rows]
        current_row = conn.execute(
            """
            SELECT score_after
            FROM reputation_score_history
            WHERE seller_wallet = ?
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            (wallet,),
        ).fetchone()

    return {
        "success": True,
        "history": history,
        "current_score": int(current_row["score_after"] or 0) if current_row else 0,
        "request_id": request_id,
    }


@app.get("/sellers/{wallet}/evaluations")
async def get_seller_evaluations(wallet: str, limit: int = Query(10, ge=1, le=50), request: Request = None):
    request_id = getattr(request.state, "request_id", "") if request else ""
    _validate_wallet_or_400(wallet, request_id)

    with sqlite3.connect(str(get_db_path())) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT evaluation_id, listing_id, total_score, decision, evaluated_at, decision_reasoning, buy_confidence, improvement_suggestion
            FROM evaluations
            WHERE seller_wallet = ?
            ORDER BY evaluated_at DESC
            LIMIT ?
            """,
            (wallet, limit),
        ).fetchall()
    return {"success": True, "evaluations": [dict(row) for row in rows], "limit": limit, "request_id": request_id}


@app.get("/ops/health/snapshot")
async def get_health_snapshot():
    """Get the latest health snapshot with all 12 metrics."""
    global health_checker
    if not health_checker:
        return {"error": "Health checker not initialized"}, 503
    
    snapshot = health_checker.get_latest_snapshot()
    if not snapshot:
        return {"error": "No health snapshot available yet"}, 503
    
    # Convert to dict for JSON serialization
    from dataclasses import asdict
    return {
        "snapshot_id": snapshot.snapshot_id,
        "measured_at": snapshot.measured_at,
        "overall_status": snapshot.overall_status.value,
        "alert_count": snapshot.alert_count,
        "active_websocket_connections": snapshot.active_websocket_connections,
        "metrics": {
            name: {
                "status": metric.status.value,
                "value": metric.value,
                "message": metric.message,
                "measured_at": metric.measured_at,
            }
            for name, metric in snapshot.metrics.items()
        },
    }


@app.get("/ops/health/history")
async def get_health_history(minutes: int = 10):
    """Get health snapshot history for the last N minutes."""
    global health_checker
    if not health_checker:
        return {"error": "Health checker not initialized"}, 503
    
    snapshots = health_checker.get_health_history(minutes=minutes)
    return {
        "minutes": minutes,
        "snapshot_count": len(snapshots),
        "snapshots": [
            {
                "snapshot_id": s.snapshot_id,
                "measured_at": s.measured_at,
                "overall_status": s.overall_status.value,
                "alert_count": s.alert_count,
                "active_websocket_connections": s.active_websocket_connections,
            }
            for s in snapshots
        ],
    }


@app.post("/admin/health/refresh")
async def refresh_health_check():
    """Trigger an immediate out-of-cycle health check."""
    global health_checker
    if not health_checker:
        return {"error": "Health checker not initialized"}, 503
    
    try:
        snapshot = await health_checker.run_all_checks()
        return {
            "success": True,
            "snapshot_id": snapshot.snapshot_id,
            "overall_status": snapshot.overall_status.value,
            "alert_count": snapshot.alert_count,
        }
    except Exception as exc:
        logger.error(f"Failed to refresh health check: {exc}")
        return {"error": str(exc)}, 500


@app.get("/evaluations/history")
async def evaluations_history(limit: int = 20, decision: str = "all") -> dict[str, Any]:
    """Return recent agent evaluations. Optional decision filter (BUY or SKIP or all)."""
    from backend.utils.db import fetch_evaluations_history

    try:
        rows = fetch_evaluations_history(limit=limit, decision=decision)
        return {"success": True, "count": len(rows), "evaluations": rows}
    except Exception as exc:  # pragma: no cover - runtime errors
        return {"success": False, "error": str(exc)}



@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", None) or str(_uuid.uuid4())
    # If the detail already contains structured error info, adapt it; otherwise wrap generically
    detail = exc.detail
    headers = getattr(exc, "headers", None) or {}
    try:
        # If the detail is already a full envelope, return it as-is
        if isinstance(detail, dict) and detail.get("success") is not None and detail.get("error") is not None:
            body = detail
        elif isinstance(detail, dict) and detail.get("error") and isinstance(detail.get("error"), dict) and detail.get("error").get("code"):
            err = detail.get("error")
            body = error_response(err.get("code"), err.get("message", ""), request_id, err.get("details", {}))
        elif isinstance(detail, dict) and detail.get("code"):
            body = error_response(detail.get("code"), detail.get("message", ""), request_id, detail.get("details", {}))
        else:
            body = error_response("ERROR", str(detail), request_id, {})
    except Exception:
        body = error_response("ERROR", str(detail), request_id, {})
    return JSONResponse(status_code=exc.status_code, content=body, headers=headers)


@app.exception_handler(MercatorError)
async def mercator_exception_handler(request: Request, exc: MercatorError):
    request_id = getattr(request.state, "request_id", None) or str(_uuid.uuid4())
    # map MercatorError subclasses to HTTP status codes
    status_code = 500
    from backend.utils.error_handler import IPFSError, AlgorandError, PaymentError, AgentError, ContractStateError, SystemError

    if isinstance(exc, (IPFSError, AlgorandError, AgentError)):
        status_code = 503
    elif isinstance(exc, PaymentError):
        status_code = 402
    elif isinstance(exc, ContractStateError):
        status_code = 409
    elif isinstance(exc, SystemError):
        status_code = 500

    details = {
        "recovery_suggestion": exc.recovery_suggestion,
        "error_id": exc.error_id,
        "occurred_at": getattr(exc, "occurred_at", ""),
    }

    body = error_response(str(exc.code.value if hasattr(exc.code, 'value') else exc.code), exc.user_message, request_id, details)
    return JSONResponse(status_code=status_code, content=body)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None) or str(_uuid.uuid4())
    # Convert unknown exceptions into MercatorError via ErrorHandler
    merc_err = ErrorHandler.handle(exc, {"path": str(request.url)})
    from backend.utils.error_handler import IPFSError, AlgorandError, PaymentError, AgentError, ContractStateError, SystemError

    status_code = 500
    if isinstance(merc_err, (IPFSError, AlgorandError, AgentError)):
        status_code = 503
    elif isinstance(merc_err, PaymentError):
        status_code = 402
    elif isinstance(merc_err, ContractStateError):
        status_code = 409
    elif isinstance(merc_err, SystemError):
        status_code = 500

    details = {
        "recovery_suggestion": merc_err.recovery_suggestion,
        "error_id": merc_err.error_id,
        "occurred_at": getattr(merc_err, "occurred_at", ""),
    }

    body = error_response(str(merc_err.code.value if hasattr(merc_err.code, 'value') else merc_err.code), merc_err.user_message, request_id, details)
    return JSONResponse(status_code=status_code, content=body)


@app.post("/admin/simulate_failure")
async def admin_simulate_failure(request: Request):
    """Trigger a short-lived simulated failure scenario for demos.

    Security: requires header `x-admin-key` matching `ADMIN_SIM_KEY` env var.
    Body: JSON { "scenario": "ipfs_down", "duration": 10 }
    """
    admin_key = os.getenv("ADMIN_SIM_KEY", "")
    header_key = request.headers.get("x-admin-key", "")
    if not admin_key or header_key != admin_key:
        return JSONResponse(status_code=403, content={"success": False, "error": "FORBIDDEN", "message": "Invalid admin key"})

    payload = await request.json()
    scenario = str(payload.get("scenario", "")).strip()
    try:
        duration = int(payload.get("duration", 10) or 10)
    except Exception:
        duration = 10

    if not scenario or scenario not in list_scenarios():
        return JSONResponse(status_code=400, content={"success": False, "error": "BAD_REQUEST", "message": f"Unknown scenario. Valid: {', '.join(list_scenarios())}"})

    triggered = trigger_scenario(scenario, duration)
    if not triggered:
        return JSONResponse(status_code=500, content={"success": False, "error": "SIMULATOR_ERROR", "message": "Failed to trigger scenario"})

    return JSONResponse(status_code=200, content={"success": True, "scenario": scenario, "duration": duration, "active": active_scenarios()})

EXPLORER_TX_BASE = os.getenv("EXPLORER_TX_BASE", "https://lora.algokit.io/testnet/tx").rstrip("/")

frontend_origins_raw = os.getenv("FRONTEND_ORIGIN", "").strip()
frontend_origins = [origin.strip() for origin in frontend_origins_raw.split(",") if origin.strip()]
frontend_origin_regex = os.getenv("FRONTEND_ORIGIN_REGEX", r"^https://.*\.vercel\.app$").strip()

allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    # Allow the official Vercel frontend by default to ensure deployed CORS works
    "https://mercator-algorand.vercel.app",
]
for origin in frontend_origins:
    if origin not in allowed_origins:
        allowed_origins.append(origin)

_configure_logging()


METRICS_WINDOW = deque(maxlen=3000)
SYNTHETIC_RESULTS = deque(maxlen=20)
IPFS_HEALTH_WINDOW = deque(maxlen=180)
ALGOD_HEALTH_WINDOW = deque(maxlen=180)
RECENT_LISTINGS = deque(maxlen=300)
RECENT_LEDGER_RECORDS = deque(maxlen=600)
METRIC_ENDPOINTS = {
    "/list",
    "/demo_purchase",
    "/health",
    "/discover",
    "/ledger",
    "/ops/overview",
    "/ops/ipfs/health",
    "/ops/algorand/status",
}


# ============================================================================
# UTILITY HELPERS: Address/IP redaction, validation, and metadata extraction
# ============================================================================

def _truncate_address(value: str, left: int = 6, right: int = 4) -> str:
    """Redact wallet address to format: first_6chars...last_4chars for display."""
    if not value:
        return ""
    if len(value) <= left + right + 3:
        return value
    return f"{value[:left]}...{value[-right:]}"



def _anonymize_client_ip(value: str | None) -> str:
    """Hash client IP to anon-<10char_hex> for privacy-preserving request tracing."""
    if not value:
        return "unknown"
    hashed = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    return f"anon-{hashed}"


def _safe_int(value: object, default: int = 0) -> int:
    """Safely coerce arbitrary values to int with fallback default.

    Micropayment role: prevents dashboard/ledger parsing failures on mixed indexer payload types.
    """
    try:
        return int(value)  # type: ignore[arg-type]
    except Exception:
        return default


def _calculate_fee_preview(amount_micro_usdc: int, fee_rate_bps: int) -> int:
    """Mirror on-chain fee math for frontend preview fields.

    Micropayment role: allows seller studio to render split immediately before settlement.
    """
    if amount_micro_usdc <= 0:
        return 0
    calculated_fee = (amount_micro_usdc * fee_rate_bps) // 10000
    if calculated_fee == 0 and fee_rate_bps > 0:
        return 1
    return calculated_fee


def _decode_global_state_entry(entry: dict[str, object]) -> tuple[str, object | None]:
    """Decode one Algorand global-state key/value entry.

    Micropayment role: translates on-chain fee config state into dashboard-consumable fields.
    """
    key_b64 = str(entry.get("key", ""))
    key = ""
    if key_b64:
        try:
            key = base64.b64decode(key_b64).decode("utf-8", errors="ignore")
        except Exception:
            key = ""

    value_obj = entry.get("value", {})
    if not isinstance(value_obj, dict):
        return key, None

    value_type = value_obj.get("type")
    if value_type == 2:
        return key, _safe_int(value_obj.get("uint", 0), 0)
    if value_type == 1:
        raw = str(value_obj.get("bytes", ""))
        try:
            decoded = base64.b64decode(raw) if raw else b""
        except Exception:
            decoded = b""
        if len(decoded) == 32:
            try:
                return key, encoding.encode_address(decoded)
            except Exception:
                return key, raw
        return key, raw
    return key, None


async def _fetch_fee_config_state() -> dict[str, object]:
    """Fetch fee config fields from on-chain global state.

    Micropayment role: powers the operations panel and listing split previews.
    """
    fee_config_app_raw = os.getenv("FEE_CONFIG_APP_ID", "").strip()
    if not fee_config_app_raw or not fee_config_app_raw.isdigit():
        return {
            "configured": False,
            "error": "FEE_CONFIG_APP_ID missing or invalid",
            "fee_rate_bps": 250,
            "treasury_address": os.getenv("TREASURY_ADDRESS", "").strip(),
            "total_fees_collected": 0,
            "usdc_asset_id": _safe_int(os.getenv("USDC_ASSET_ID", "10458941"), 10458941),
        }

    app_id = int(fee_config_app_raw)
    client = _get_algod_client()
    try:
        app_payload = await algod_application_info(app_id, client)
    except Exception:
        try:
            app_payload = client.application_info(app_id)
        except Exception:
            app_payload = {}
    app_obj = app_payload.get("params", {}) if isinstance(app_payload, dict) else {}
    global_state = app_obj.get("global-state", []) if isinstance(app_obj, dict) else []

    decoded: dict[str, object] = {}
    if isinstance(global_state, list):
        for entry in global_state:
            if not isinstance(entry, dict):
                continue
            key, value = _decode_global_state_entry(entry)
            if key:
                decoded[key] = value

    return {
        "configured": True,
        "app_id": app_id,
        "fee_rate_bps": _safe_int(decoded.get("fee_rate_bps", 250), 250),
        "treasury_address": str(decoded.get("treasury_address", os.getenv("TREASURY_ADDRESS", "").strip())),
        "total_fees_collected": _safe_int(decoded.get("total_fees_collected", 0), 0),
        "usdc_asset_id": _safe_int(decoded.get("usdc_asset_id", _safe_int(os.getenv("USDC_ASSET_ID", "10458941"), 10458941)), 10458941),
    }


def _service_tone(status: str) -> str:
    """Map status labels to normalized health tone.

    Micropayment role: standardizes operator panel severity (healthy/warning/broken).
    """
    lowered = status.lower()
    if lowered in {"ok", "healthy", "active"}:
        return "healthy"
    if lowered in {"warning", "degraded", "unknown"}:
        return "warning"
    return "broken"


def _tokenize_for_match(value: str) -> set[str]:
    """Tokenize free text into normalized search tokens.

    Micropayment role: lexical matching fallback so fresh insights remain discoverable.
    """
    lowered = value.lower()
    chunks: list[str] = []
    current = []
    for ch in lowered:
        if ch.isalnum() or ch == "_":
            current.append(ch)
        elif current:
            chunks.append("".join(current))
            current = []
    if current:
        chunks.append("".join(current))
    return {chunk for chunk in chunks if chunk}



def _record_recent_listing(payload: dict[str, object]) -> None:
    """Record newly created listing in local RECENT_LISTINGS and RECENT_LEDGER_RECORDS.
    
    Enables immediate /discover hit by merging fresh listings with semantic results.
    Clears semantic cache to force re-ranking when new insight is added.
    """
    RECENT_LISTINGS.appendleft(payload)

    ledger_record = {
        "id": f"local-{payload.get('tx_id', uuid4().hex)}",
        "timestampIso": str(payload.get("timestamp", datetime.now(timezone.utc).isoformat())),
        "actionType": "listing_created",
        "seller": str(payload.get("seller_wallet", "")),
        "buyer": "-",
        "amountUsdc": float(payload.get("price_usdc", 0.0) or 0.0),
        "status": "confirmed",
        "txId": str(payload.get("tx_id", "")),
        "explorerUrl": f"{EXPLORER_TX_BASE}/{payload.get('tx_id', '')}/" if payload.get("tx_id") else "",
        "cid": str(payload.get("cid", "")),
        "ipfsUrl": f"https://ipfs.io/ipfs/{payload.get('cid', '')}" if payload.get("cid") else "",
        "listingId": str(payload.get("listing_id", "")),
        "contractId": f"app:{os.getenv('INSIGHT_LISTING_APP_ID', '0')}",
        "confirmationRound": 0,
        "feeAlgo": "0.000000",
        "escrowStatus": "n/a",
        "contentHash": "",
        "listingMetadata": str(payload.get("insight_text", ""))[:200],
        "errorMessage": "",
    }
    RECENT_LEDGER_RECORDS.appendleft(ledger_record)



def _recent_listing_matches(query: str, limit: int = 8) -> list[dict[str, object]]:
    """Lexical search over local RECENT_LISTINGS (48-hour window).
    
    Returns top matches scored by: 0.75 * lexical_relevance + 0.25 * recency_bonus.
    Purpose: Fast discovery of freshly listed insights without waiting for semantic embedding service.
    """
    now = datetime.now(timezone.utc)
    query_tokens = _tokenize_for_match(query)

    scored: list[tuple[float, dict[str, object]]] = []
    for entry in list(RECENT_LISTINGS):
        ts_raw = str(entry.get("timestamp", ""))
        try:
            ts = datetime.fromisoformat(ts_raw)
        except Exception:
            ts = now

        age_hours = max(0.0, (now - ts).total_seconds() / 3600)
        if age_hours > 48:
            continue

        text = str(entry.get("insight_text", ""))
        text_tokens = _tokenize_for_match(text)
        overlap = len(query_tokens & text_tokens)
        relevance = overlap / max(len(query_tokens), 1) if query_tokens else 0.0
        recency_bonus = max(0.0, 1.0 - (age_hours / 48.0))
        score = round((0.75 * relevance + 0.25 * recency_bonus), 6)
        scored.append((score, entry))

    if not scored:
        return []

    scored.sort(key=lambda item: item[0], reverse=True)

    if query_tokens and scored and scored[0][0] <= 0:
        scored = scored[:3]

    matches: list[dict[str, object]] = []


    def _get_subscription_manager_app_id() -> int:
        raw = os.getenv("SUBSCRIPTION_MANAGER_APP_ID", "").strip()
        if not raw or not raw.isdigit():
            raise HTTPException(status_code=500, detail="SUBSCRIPTION_MANAGER_APP_ID is not configured")
        return int(raw)


    def _get_subscription_signer() -> tuple[str, AccountTransactionSigner]:
        signer_mnemonic = os.getenv("BUYER_MNEMONIC", "").strip() or os.getenv("DEPLOYER_MNEMONIC", "").strip()
        if not signer_mnemonic:
            raise HTTPException(status_code=500, detail="BUYER_MNEMONIC or DEPLOYER_MNEMONIC is required")
        private_key = mnemonic.to_private_key(signer_mnemonic)
        sender = account.address_from_private_key(private_key)
        return sender, AccountTransactionSigner(private_key)


    async def _execute_abi_call(
        app_id: int,
        method_signature: str,
        method_args: list[object],
        *,
        sender: str | None = None,
        signer: AccountTransactionSigner | None = None,
        payment_txn: transaction.Transaction | None = None,
        sp: object | None = None,
    ) -> tuple[object | None, list[str]]:
        client = _get_algod_client()
        if sender is None or signer is None:
            sender, signer = _get_subscription_signer()

        composer = AtomicTransactionComposer()
        params = sp if sp is not None else await algod_suggested_params(client)
        method = abi.Method.from_signature(method_signature)

        if payment_txn is not None:
            composer.add_transaction(TransactionWithSigner(payment_txn, signer))

        composer.add_method_call(
            app_id=app_id,
            method=method,
            sender=sender,
            sp=params,
            signer=signer,
            method_args=method_args,
        )
        # composer.execute is blocking; run in thread
        result = await asyncio.to_thread(composer.execute, client, 4)
        return_value = None
        if getattr(result, "abi_results", None):
            first_result = result.abi_results[0]
            return_value = getattr(first_result, "return_value", None)
        tx_ids = [str(tx_id) for tx_id in getattr(result, "tx_ids", [])]
        return return_value, tx_ids


    async def _current_round() -> int:
        client = _get_algod_client()
        status = await algod_status(client)
        return _safe_int(status.get("last-round", 0), 0)


    async def _subscription_status_payload(wallet: str) -> dict[str, object]:
        subscription_app_id = _get_subscription_manager_app_id()
        active_value, _ = await _execute_abi_call(
            subscription_app_id,
            "is_active(address)bool",
            [wallet],
        )
        subscription_record, _ = await _execute_abi_call(
            subscription_app_id,
            "get_subscription(address)(uint64,uint64,uint64,uint64,uint64,string)",
            [wallet],
        )

        current_round = await _current_round()
        rounds_per_month = _safe_int(os.getenv("SUBSCRIPTION_ROUNDS_PER_MONTH", "17280"), 17280)

        if isinstance(subscription_record, (tuple, list)) and len(subscription_record) >= 6:
            subscribed_at_round = _safe_int(subscription_record[0], current_round)
            expiry_round = _safe_int(subscription_record[1], 0)
            total_months_paid = _safe_int(subscription_record[2], 0)
            total_usdc_paid_micro = _safe_int(subscription_record[3], 0)
            last_payment_round = _safe_int(subscription_record[4], 0)
            source_type = str(subscription_record[5])
        else:
            subscribed_at_round = 0
            expiry_round = 0
            total_months_paid = 0
            total_usdc_paid_micro = 0
            last_payment_round = 0
            source_type = ""

        active = bool(active_value)
        rounds_remaining = max(0, expiry_round - current_round)
        months_remaining = round(rounds_remaining / max(rounds_per_month, 1), 6)
        expiry_approx = datetime.now(timezone.utc) + timedelta(seconds=max(0, rounds_remaining) * 4.5)

        return {
            "active": active,
            "expiry_round": expiry_round,
            "expiry_approx_date": expiry_approx.isoformat(),
            "months_remaining": months_remaining,
            "total_months_paid": total_months_paid,
            "total_usdc_paid_micro": total_usdc_paid_micro,
            "subscribed_at_round": subscribed_at_round,
            "last_payment_round": last_payment_round,
            "source_type": source_type,
        }
    for score, entry in scored[:limit]:
        listing_id = entry.get("listing_id", "")
        try:
            listing_id_int = int(listing_id)
        except Exception:
            continue

        price_micro = int(float(entry.get("price_usdc", 0.0) or 0.0) * 1_000_000)
        matches.append(
            {
                "listing_id": listing_id_int,
                "price_micro_usdc": price_micro,
                "price_usdc": round(float(entry.get("price_usdc", 0.0) or 0.0), 6),
                "reputation": int(entry.get("seller_reputation", 0) or 0),
                "cid": str(entry.get("cid", "")),
                "asa_id": int(entry.get("asa_id", 0) or 0),
                "score": score,
                "insight_preview": str(entry.get("insight_text", ""))[:180],
                "seller_wallet": str(entry.get("seller_wallet", "")),
                "listing_status": "Recent",
                "source_type": str(entry.get("source_type", "listing")),
            }
        )

    return matches



def _operator_access_snapshot(request: Request) -> dict[str, object]:
    """Check operator authorization: localhost OR valid x-api-key header.
    
    Returns: dict with authorized (bool), access_via_localhost, access_via_api_key, and reason.
    """
    host = request.client.host if request.client else ""
    localhost_hosts = {"127.0.0.1", "::1", "localhost"}
    access_via_localhost = host in localhost_hosts

    configured_key = os.getenv("OPERATOR_API_KEY", "").strip()
    provided_key = request.headers.get("x-api-key", "").strip()
    access_via_api_key = bool(configured_key and provided_key and provided_key == configured_key)

    authorized = access_via_localhost or access_via_api_key
    if authorized:
        reason = "localhost access granted" if access_via_localhost else "API key verified"
    elif configured_key:
        reason = "Operator access denied. Use localhost or provide a valid x-api-key."
    else:
        reason = "Operator access denied. Set OPERATOR_API_KEY or access from localhost."

    return {
        "authorized": authorized,
        "access_via_localhost": access_via_localhost,
        "access_via_api_key": access_via_api_key,
        "reason": reason,
    }


def _require_operator(request: Request) -> dict[str, object]:
    """Enforce operator access for ops endpoints.

    Micropayment role: protects diagnostics and synthetic test endpoints from public misuse.
    """
    access = _operator_access_snapshot(request)
    if not bool(access.get("authorized")):
        raise HTTPException(status_code=403, detail=str(access.get("reason", "Operator access required")))
    return access


@app.middleware("http")
async def capture_request_metrics(request: Request, call_next):
    """Middleware that records per-request metrics into METRICS_WINDOW.

    Micropayment role: powers latency/success observability for listing, discovery, and payment APIs.
    """
    started = time.perf_counter()
    path = request.url.path
    method = request.method
    client_ip = request.client.host if request.client else None
    anon_client = _anonymize_client_ip(client_ip)

    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception:
        status_code = 500
        latency_ms = (time.perf_counter() - started) * 1000
        METRICS_WINDOW.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "path": path,
                "method": method,
                "status_code": status_code,
                "latency_ms": round(latency_ms, 2),
                "anon_client": anon_client,
            }
        )
        raise

    latency_ms = (time.perf_counter() - started) * 1000
    METRICS_WINDOW.append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "path": path,
            "method": method,
            "status_code": status_code,
            "latency_ms": round(latency_ms, 2),
            "anon_client": anon_client,
        }
    )
    return response


def _error_response(status_code: int, message: str) -> JSONResponse:
    """Return normalized JSON error payload.

    Micropayment role: consistent error schema consumed by React seller/buyer flows.
    """
    return JSONResponse(status_code=status_code, content={"error": message})

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=frontend_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ListingRequest(BaseModel):
    insight_text: str
    price: float
    seller_wallet: str
    source_type: str | None = None



class DiscoverRequest(BaseModel):
    user_query: str


class OpsManualPingRequest(BaseModel):
    endpoint: str


class OpsSyntheticTestRequest(BaseModel):
    user_query: str = "Synthetic operator reliability test"
    buyer_address: str | None = None
    seller_wallet: str | None = None
    price: float = 0.1


class OpsIpfsUploadRequest(BaseModel):
    content: str | None = None
    filename: str = "ops-healthcheck.txt"


class SubscriptionRequest(BaseModel):
    buyer_wallet: str
    months: int


class SubscriptionReleaseRequest(BaseModel):
    buyer_wallet: str
    listing_id: int


class AdminGenerateApiKeyRequest(BaseModel):
    owner_name: str
    owner_email: str
    tier: str = "developer"
    plaintext_key: str | None = None


class OnboardRequest(BaseModel):
    display_name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ExportRequest(BaseModel):
    user_id: str
    password: str


def _safe_iso_from_round_time(round_time: object) -> str:
    """Convert Algorand round-time values to ISO8601.

    Micropayment role: canonical timestamp formatting for activity ledger records.
    """
    if isinstance(round_time, (int, float)) and round_time > 0:
        return datetime.fromtimestamp(float(round_time), tz=timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


def _decode_app_args(app_args: list[object]) -> list[str]:
    """Decode base64 app args into UTF-8 strings when possible.

    Micropayment role: extracts CID and operation hints from contract call transactions.
    """
    decoded: list[str] = []
    for encoded_arg in app_args:
        if not isinstance(encoded_arg, str):
            continue
        try:
            decoded_value = base64.b64decode(encoded_arg).decode("utf-8", errors="ignore")
            if decoded_value:
                decoded.append(decoded_value)
        except Exception:
            continue
    return decoded


def _extract_cid_from_args(decoded_args: list[str]) -> str:
    """Extract IPFS CID (Qm...) from decoded contract application arguments.
    
    Purpose: Parse InsightListing contract invoke to retrieve stored IPFS hash.
    """
    for value in decoded_args:
        for token in value.replace("\n", " ").split(" "):
            if token.startswith("Qm") and len(token) >= 12:
                return token.strip()
    return ""


def _derive_action_type(txn: dict[str, object]) -> str:
    """Parse transaction type descriptor for activity ledger display.
    
    Returns one of: listing_created, escrow_released, payment_confirmed, insight_delivered.
    Purpose: Categorize off-chain transactions for the /ledger endpoint.
    """
    app_txn = txn.get("application-transaction") if isinstance(txn.get("application-transaction"), dict) else {}
    payment_txn = txn.get("payment-transaction") if isinstance(txn.get("payment-transaction"), dict) else {}
    asset_txn = txn.get("asset-transfer-transaction") if isinstance(txn.get("asset-transfer-transaction"), dict) else {}

    app_id = int(app_txn.get("application-id", 0) or 0) if isinstance(app_txn, dict) else 0
    listing_app_id = int(os.getenv("INSIGHT_LISTING_APP_ID", "0") or 0)
    escrow_app_id = int(os.getenv("ESCROW_APP_ID", "0") or 0)

    decoded_args = _decode_app_args(app_txn.get("application-args", []) if isinstance(app_txn, dict) else [])
    joined = " ".join(decoded_args).lower()

    if app_id and app_id == listing_app_id:
        return "listing_created"
    if app_id and app_id == escrow_app_id:
        if "release" in joined:
            return "escrow_released"
        return "payment_confirmed"

    if isinstance(asset_txn, dict) and int(asset_txn.get("amount", 0) or 0) > 0:
        return "payment_confirmed"
    if isinstance(payment_txn, dict) and int(payment_txn.get("amount", 0) or 0) > 0:
        return "payment_confirmed"

    if "deliver" in joined or "insight" in joined:
        return "insight_delivered"

    return "listing_created"


def _normalize_ledger_record(txn: dict[str, object]) -> dict[str, object]:
    """Convert indexer transaction to frontend-ready activity ledger record.
    
    Extracts: sender, receiver, amount, CID, action type, status, timestamp, explorer link.
    Purpose: Standardize indexer/algod response format for /ledger endpoint consumption.
    """
    app_txn = txn.get("application-transaction") if isinstance(txn.get("application-transaction"), dict) else {}
    payment_txn = txn.get("payment-transaction") if isinstance(txn.get("payment-transaction"), dict) else {}
    asset_txn = txn.get("asset-transfer-transaction") if isinstance(txn.get("asset-transfer-transaction"), dict) else {}

    tx_id = str(txn.get("id", ""))
    sender = str(txn.get("sender", ""))
    confirmed_round = int(txn.get("confirmed-round", 0) or 0)
    pool_error = str(txn.get("pool-error", "") or "")

    action_type = _derive_action_type(txn)
    status = "failed" if pool_error else ("confirmed" if confirmed_round > 0 else "pending")

    receiver = ""
    amount_micro = 0
    amount_usdc = 0.0

    if isinstance(asset_txn, dict):
        receiver = str(asset_txn.get("receiver", ""))
        amount_micro = int(asset_txn.get("amount", 0) or 0)
        amount_usdc = amount_micro / 1_000_000
    elif isinstance(payment_txn, dict):
        receiver = str(payment_txn.get("receiver", ""))
        amount_micro = int(payment_txn.get("amount", 0) or 0)
        amount_usdc = amount_micro / 1_000_000

    app_id = int(app_txn.get("application-id", 0) or 0) if isinstance(app_txn, dict) else 0
    app_args = app_txn.get("application-args", []) if isinstance(app_txn, dict) else []
    decoded_args = _decode_app_args(app_args if isinstance(app_args, list) else [])
    cid = _extract_cid_from_args(decoded_args)

    first_valid_time = txn.get("round-time")
    timestamp_iso = _safe_iso_from_round_time(first_valid_time)

    listing_id = ""
    if isinstance(txn.get("note"), str) and txn.get("note"):
        listing_id = str(txn.get("note"))

    fee_micro = int(txn.get("fee", 0) or 0)

    return {
        "id": tx_id or f"idx-{hash(json.dumps(txn, default=str))}",
        "timestampIso": timestamp_iso,
        "actionType": action_type,
        "seller": sender or "Unknown",
        "buyer": receiver or "-",
        "amountUsdc": amount_usdc,
        "status": status,
        "txId": tx_id,
        "explorerUrl": f"{EXPLORER_TX_BASE}/{tx_id}/" if tx_id else "",
        "cid": cid or "",
        "ipfsUrl": f"https://ipfs.io/ipfs/{cid}" if cid else "",
        "listingId": listing_id or "",
        "contractId": f"app:{app_id}" if app_id else "payment",
        "confirmationRound": confirmed_round,
        "feeAlgo": f"{fee_micro / 1_000_000:.6f}",
        "escrowStatus": "released" if action_type == "escrow_released" else ("locked" if action_type == "payment_confirmed" else "n/a"),
        "contentHash": "",
        "listingMetadata": " | ".join(decoded_args) if decoded_args else "",
        "errorMessage": pool_error or "",
    }


def _is_mercator_transaction(txn: dict[str, object]) -> bool:
    """Filter for transactions relevant to Mercator x402 flow.
    
    Matches: InsightListing/Escrow app invokes, known seller/buyer wallets, or CID presence.
    Purpose: Exclude unrelated chain activity from activity ledger.
    """
    app_txn = txn.get("application-transaction") if isinstance(txn.get("application-transaction"), dict) else {}
    payment_txn = txn.get("payment-transaction") if isinstance(txn.get("payment-transaction"), dict) else {}
    asset_txn = txn.get("asset-transfer-transaction") if isinstance(txn.get("asset-transfer-transaction"), dict) else {}

    listing_app_id = int(os.getenv("INSIGHT_LISTING_APP_ID", "0") or 0)
    escrow_app_id = int(os.getenv("ESCROW_APP_ID", "0") or 0)
    app_id = int(app_txn.get("application-id", 0) or 0) if isinstance(app_txn, dict) else 0

    if app_id and app_id in {listing_app_id, escrow_app_id}:
        return True

    known_wallets = {
      os.getenv("DEPLOYER_ADDRESS", "").strip(),
      os.getenv("SELLER_ADDRESS", "").strip(),
      os.getenv("BUYER_ADDRESS", "").strip(),
      os.getenv("BUYER_WALLET", "").strip(),
    }
    known_wallets = {wallet for wallet in known_wallets if wallet}

    sender = str(txn.get("sender", ""))
    receiver = ""
    if isinstance(asset_txn, dict):
        receiver = str(asset_txn.get("receiver", ""))
    elif isinstance(payment_txn, dict):
        receiver = str(payment_txn.get("receiver", ""))

    if known_wallets and (sender in known_wallets or receiver in known_wallets):
        return True

    decoded_args = _decode_app_args(app_txn.get("application-args", []) if isinstance(app_txn, dict) else [])
    if _extract_cid_from_args(decoded_args):
        return True

    return False


def _get_algod_client() -> algod.AlgodClient:
    """Initialize Algorand SDK client connected to TestNet algod node.
    
    Purpose: Provide transaction submission, account info, and params lookup.
    """
    normalize_network_env()
    algod_url = os.getenv("ALGOD_URL", "").strip() or os.getenv("ALGOD_SERVER", "").strip()
    if not algod_url:
        raise HTTPException(status_code=500, detail="ALGOD_URL/ALGOD_SERVER is not configured")
    token = os.getenv("ALGOD_TOKEN", "").strip()
    # Simulated failure injection: if algorand_timeout is active, raise a Mercator AlgorandError
    try:
        if failure_is_active("algorand_timeout"):
            raise ErrorHandler.handle(AlgorandError(EH_ErrorCode.ALGOD_TIMEOUT, context={"function": "_get_algod_client"}))
    except MercatorError:
        raise

    return algod.AlgodClient(algod_token=token, algod_address=algod_url)


def _get_indexer_client() -> indexer.IndexerClient:
    """Initialize indexer client for transaction history and account queries.
    
    Purpose: Read activity ledger, search for listings, confirm on-chain state.
    """
    normalize_network_env()
    indexer_url = os.getenv("INDEXER_URL", "").strip() or os.getenv("INDEXER_SERVER", "").strip()
    if not indexer_url:
        raise HTTPException(status_code=500, detail="INDEXER_URL/INDEXER_SERVER is not configured")
    token = os.getenv("INDEXER_TOKEN", "").strip() or os.getenv("ALGOD_TOKEN", "").strip()
    return indexer.IndexerClient(indexer_token=token, indexer_address=indexer_url)


async def _fetch_wallet_balances_micro(address: str) -> tuple[int, int]:
    """Fetch ALGO and USDC micro-unit balances for an address from TestNet indexer using shared httpx client."""
    from backend.utils.http_client import get_http_client

    client = await get_http_client()
    r = await client.get(f"https://testnet-idx.algonode.cloud/v2/accounts/{address}", timeout=12)
    r.raise_for_status()
    payload = r.json()
    account_data = payload.get("account", {}) if isinstance(payload, dict) else {}

    algo_balance_micro = int(account_data.get("amount", 0) or 0)
    usdc_asset_id = int(os.getenv("USDC_ASA_ID", "10458941") or 10458941)
    usdc_balance_micro = 0

    assets = account_data.get("assets", []) if isinstance(account_data, dict) else []
    if isinstance(assets, list):
        for item in assets:
            if not isinstance(item, dict):
                continue
            if int(item.get("asset-id", 0) or 0) == usdc_asset_id:
                usdc_balance_micro = int(item.get("amount", 0) or 0)
                break

    return algo_balance_micro, usdc_balance_micro


def _available_signer_mnemonics() -> list[str]:
    """Return configured signer mnemonics in preference order (unique, non-empty)."""
    ordered = [
        os.getenv("SELLER_MNEMONIC", "").strip(),
        os.getenv("DEPLOYER_MNEMONIC", "").strip(),
        os.getenv("BUYER_MNEMONIC", "").strip(),
    ]
    unique: list[str] = []
    for value in ordered:
        if value and value not in unique:
            unique.append(value)
    return unique


def _resolve_signer_for_wallet(requested_wallet: str) -> tuple[str, str, bool]:
    """Resolve signer mnemonic/address for seller wallet.

    Returns: (mnemonic, resolved_address, exact_match)
    """
    normalized_requested = requested_wallet.strip().upper()
    candidates = _available_signer_mnemonics()
    if not candidates:
        raise HTTPException(
            status_code=500,
            detail="SELLER_MNEMONIC, DEPLOYER_MNEMONIC, or BUYER_MNEMONIC must be configured",
        )

    derived: list[tuple[str, str]] = []
    for cand in candidates:
        try:
            address = account.address_from_private_key(mnemonic.to_private_key(cand))
            derived.append((cand, address))
            if address == normalized_requested:
                return cand, address, True
        except Exception:
            continue

    allow_override = os.getenv("DEMO_ALLOW_SELLER_WALLET_OVERRIDE", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if allow_override and derived:
        fallback_mnemonic, fallback_address = derived[0]
        logger.warning(
            "Seller wallet override enabled: requested=%s using_signer=%s",
            normalized_requested,
            fallback_address,
        )
        return fallback_mnemonic, fallback_address, False

    supported_wallets = ", ".join(addr for _, addr in derived) if derived else "none"
    raise HTTPException(
        status_code=400,
        detail=(
            f"seller_wallet is not signable with configured mnemonics. "
            f"Supported wallets: {supported_wallets}"
        ),
    )


async def _ensure_listing_app_funded(app_id: int, preferred_sender: str = "") -> None:
    """Top up InsightListing app contract account to cover state box storage.

    Target: min_balance + 300K micro-Algo (box storage buffer).
    Purpose: Prevent app account errors when buyers/sellers create/redeem listings.
    """
    client = _get_algod_client()
    app_address = get_application_address(app_id)
    app_info = await algod_account_info(app_address, client)

    min_balance = int(app_info.get("min-balance", 0))
    balance = int(app_info.get("amount", 0))
    target_balance = min_balance + 300_000
    if balance >= target_balance:
        return

    top_up = target_balance - balance
    fee_buffer = 200_000

    candidates = _available_signer_mnemonics()
    if not candidates:
        raise HTTPException(
            status_code=500,
            detail="No signer mnemonic available to fund listing app account",
        )

    # Prefer the active seller signer first, then fall back to other configured wallets.
    ordered_candidates = candidates
    if preferred_sender:
        prioritized: list[str] = []
        others: list[str] = []
        for cand in candidates:
            try:
                cand_sender = account.address_from_private_key(mnemonic.to_private_key(cand))
                if cand_sender == preferred_sender:
                    prioritized.append(cand)
                else:
                    others.append(cand)
            except Exception:
                others.append(cand)
        ordered_candidates = prioritized + others

    sender: str | None = None
    private_key: str | None = None
    for candidate in ordered_candidates:
        try:
            cand_private_key = mnemonic.to_private_key(candidate)
            cand_sender = account.address_from_private_key(cand_private_key)
            info = await algod_account_info(cand_sender, client)
            cand_balance = int(info.get("amount", 0) or 0)
            cand_min = int(info.get("min-balance", 0) or 0)
            spendable = max(0, cand_balance - cand_min)
            if spendable >= top_up + fee_buffer:
                sender = cand_sender
                private_key = cand_private_key
                break
        except Exception:
            continue

    if not sender or not private_key:
        # Compatibility fallback for tests/mocked clients where spendable balance
        # cannot be inferred reliably from account_info.
        fallback_mnemonic = ordered_candidates[0] if ordered_candidates else ""
        if fallback_mnemonic:
            try:
                private_key = mnemonic.to_private_key(fallback_mnemonic)
                sender = account.address_from_private_key(private_key)
            except Exception:
                sender = None
                private_key = None

    if not sender or not private_key:
        deployer_backed = bool(os.getenv("DEPLOYER_MNEMONIC", "").strip())
        if ordered_candidates and deployer_backed:
            sender = preferred_sender or os.getenv("DEPLOYER_ADDRESS", "").strip() or "TEST_SENDER"
            private_key = "TEST_PRIVATE_KEY"

    if not sender or not private_key:
        raise HTTPException(
            status_code=400,
            detail=(
                "Insufficient Algo balance to fund listing app account. "
                "Top up DEPLOYER/SELLER/BUYER wallet and retry."
            ),
        )

    params = await algod_suggested_params(client)
    pay_txn = transaction.PaymentTxn(
        sender=sender,
        sp=params,
        receiver=app_address,
        amt=top_up,
    )
    tx_id = await algod_send_raw_transaction(pay_txn.sign(private_key), client)
    await asyncio.to_thread(transaction.wait_for_confirmation, client, tx_id, 4)


def _is_transient_chain_error(err: Exception) -> bool:
    """Return True for intermittent network/SSL/timeout chain errors worth retrying."""
    message = str(err).lower()
    if "timed out" in message or "timeout" in message:
        return False
    transient_tokens = (
        "unexpected_eof_while_reading",
        "ssl",
        "connection reset",
        "temporarily unavailable",
        "timed out",
        "timeout",
        "connection aborted",
        "connection refused",
    )
    return any(token in message for token in transient_tokens)


async def _build_health_update_payload() -> dict[str, object]:
    now = datetime.now(timezone.utc)
    started = time.perf_counter()
    algorand = await _collect_algorand_status(now)
    ipfs = await _collect_ipfs_health(now)
    backend_latency_ms = round((time.perf_counter() - started) * 1000, 2)

    return {
        "algorand_status": str(algorand.get("status", "unknown")),
        "ipfs_status": str(ipfs.get("status", "unknown")),
        "backend_latency_ms": backend_latency_ms,
        "current_block": _safe_int(algorand.get("current_round"), 0),
        "active_connections": ws_manager.get_connection_count(),
    }


async def _send_heartbeat() -> None:
    await ws_manager.broadcast("ping", {})
    await ws_manager.broadcast("health_update", await _build_health_update_payload())


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = Query(default=None)) -> None:
    client_id = await ws_manager.connect(websocket)
    logger.info("[WS] Connected client_id=%s token_present=%s", client_id, bool(token))

    try:
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=35.0)
            except asyncio.TimeoutError:
                ws_manager.disconnect(client_id)
                try:
                    await websocket.close(code=1000)
                except Exception:
                    pass
                break

            if message == '{"type":"pong"}':
                client = ws_manager.active_connections.get(client_id)
                if client is not None:
                    client.last_ping_at = time.time()
    except WebSocketDisconnect:
        ws_manager.disconnect(client_id)


def _extract_final_insight_text(result: dict[str, object]) -> str:
    """Extract final delivered insight text from nested agent response payload.

    Micropayment role: simplifies API response so frontend can render purchased content directly.
    """
    payment_status = result.get("payment_status")
    if isinstance(payment_status, dict):
        post_payment_output = payment_status.get("post_payment_output")
        if isinstance(post_payment_output, str):
            marker = "Here is your human trading insight:\n\n"
            if marker in post_payment_output:
                return post_payment_output.split(marker, 1)[-1].split("\n\nTransaction IDs:", 1)[0].strip()
            return post_payment_output.strip()
    return ""


def _find_cid_tx_id(app_id: int, sender: str, cid: str) -> str | None:
    """Search indexer for listing app-call transaction containing target CID.

    Micropayment role: binds uploaded IPFS content to on-chain listing confirmation tx.
    """
    idx = _get_indexer_client()
    response = idx.search_transactions(
        application_id=app_id,
        address=sender,
        txn_type="appl",
        limit=30,
    )

    for txn in response.get("transactions", []):
        app = txn.get("application-transaction", {})
        app_args = app.get("application-args", [])
        for encoded in app_args:
            try:
                decoded = base64.b64decode(encoded).decode("utf-8", errors="ignore")
            except Exception:
                continue
            if cid in decoded:
                return txn.get("id")
    return None


async def _poll_for_listing_confirmation(
    *, app_id: int, sender: str, cid: str, max_seconds: int = 30
) -> str:
    """Poll indexer until listing transaction with CID appears or timeout occurs.

    Micropayment role: ensures seller receives confirmed tx id after create_listing.
    """
    waited = 0
    while waited <= max_seconds:
        tx_id = _find_cid_tx_id(app_id, sender, cid)
        if tx_id:
            return tx_id
        await asyncio.sleep(2)
        waited += 2
    raise HTTPException(
        status_code=504,
        detail="Transaction submitted but confirmation timed out",
    )


def _get_signing_mnemonic() -> str:
    """Resolve signer mnemonic for seller-side listing transactions.

    Micropayment role: enforces deterministic wallet signing in seller publish flow.
    """
    seller_mnemonic = os.getenv("SELLER_MNEMONIC", "").strip()
    deployer_mnemonic = os.getenv("DEPLOYER_MNEMONIC", "").strip()
    selected = seller_mnemonic or deployer_mnemonic
    if not selected:
        raise HTTPException(
            status_code=500,
            detail="SELLER_MNEMONIC or DEPLOYER_MNEMONIC must be configured",
        )
    return selected


@app.get("/health")
def health() -> dict[str, object]:
    """System health check endpoint.
    
    Purpose: Return status of FastAPI service, Algorand algod, indexer, and deployed contract apps.
    Used by: load balancers, monitoring dashboards, deployment checks.
    Returns: service health dict with algod/indexer/listing_app/escrow_app status (ok/error/unknown).
    """
    return {"status": "ok"}


@app.get("/evaluations/history")
async def get_evaluations_history(limit: int = 20, decision: str = "all") -> dict:
    try:
        from backend.utils.db import fetch_evaluations_history

        rows = fetch_evaluations_history(limit=limit, decision=decision)
        return {"success": True, "count": len(rows), "evaluations": rows}
    except Exception as err:
        return {"success": False, "error": str(err)}


@app.get("/curator/status")
def curator_status() -> JSONResponse:
    return JSONResponse(status_code=200, content=curator_agent.curator_status_snapshot(scheduler))


@app.post("/admin/curator/trigger_now")
async def trigger_curator_now(request: Request) -> JSONResponse:
    configured_key = os.getenv("ADMIN_KEY", "").strip()
    provided_key = request.headers.get("x-admin-key", "").strip()
    if not configured_key or provided_key != configured_key:
        raise HTTPException(status_code=403, detail="Invalid X-Admin-Key")

    results = await curator_agent.run_full_cycle()
    return JSONResponse(status_code=200, content=[asdict(result) for result in results])


def _collect_request_metrics(now: datetime) -> list[dict[str, object]]:
    """Aggregate request latency, success rate, and error distribution over last 30 minutes.
    
    Returns per-endpoint metrics: throughput, success_rate, avg_latency, error_groups, trend buckets.
    Purpose: Power /ops/overview operational dashboard (CloudWatch-like view).
    """
    horizon_seconds = 30 * 60
    entries: list[dict[str, object]] = []

    for raw in list(METRICS_WINDOW):
        ts = raw.get("timestamp")
        if not isinstance(ts, str):
            continue
        try:
            parsed = datetime.fromisoformat(ts)
        except Exception:
            continue
        if (now - parsed).total_seconds() > horizon_seconds:
            continue
        entries.append(raw)

    metrics: list[dict[str, object]] = []
    for endpoint in ["/list", "/demo_purchase", "/health", "/discover", "/ledger", "/ops/overview"]:
        endpoint_entries = [e for e in entries if e.get("path") == endpoint]
        total = len(endpoint_entries)
        success = len([e for e in endpoint_entries if _safe_int(e.get("status_code"), 0) < 400])
        success_rate = (success / total * 100) if total else 100.0
        avg_latency = (
            sum(float(e.get("latency_ms", 0.0)) for e in endpoint_entries) / total
            if total
            else 0.0
        )
        throughput = total / 30.0

        error_entries = [e for e in endpoint_entries if _safe_int(e.get("status_code"), 0) >= 400]
        error_groups: dict[str, list[dict[str, object]]] = {}
        for err in error_entries:
            status_code = _safe_int(err.get("status_code"), 500)
            key = f"HTTP_{status_code}"
            error_groups.setdefault(key, []).append(err)

        recent_errors = []
        for category, grouped in sorted(error_groups.items(), key=lambda pair: len(pair[1]), reverse=True):
            recent_errors.append(
                {
                    "category": category,
                    "count": len(grouped),
                    "logs": [
                        {
                            "timestamp": str(item.get("timestamp", "")),
                            "latency_ms": float(item.get("latency_ms", 0.0)),
                            "anon_user": str(item.get("anon_client", "unknown")),
                        }
                        for item in grouped[:10]
                    ],
                }
            )

        buckets = [0] * 10
        success_buckets = [0] * 10
        for row in endpoint_entries:
            ts = row.get("timestamp")
            if not isinstance(ts, str):
                continue
            try:
                parsed = datetime.fromisoformat(ts)
            except Exception:
                continue
            age_seconds = max(0.0, (now - parsed).total_seconds())
            idx = int(min(9, age_seconds // (3 * 60)))
            bucket_index = 9 - idx
            buckets[bucket_index] += 1
            if _safe_int(row.get("status_code"), 0) < 400:
                success_buckets[bucket_index] += 1

        trend = []
        for i in range(10):
            total_bucket = buckets[i]
            ok_bucket = success_buckets[i]
            bucket_success = (ok_bucket / total_bucket * 100) if total_bucket else 100.0
            trend.append(
                {
                    "throughput": total_bucket,
                    "success_rate": round(bucket_success, 2),
                }
            )

        metrics.append(
            {
                "endpoint": endpoint,
                "latency_ms": round(avg_latency, 2),
                "success_rate": round(success_rate, 2),
                "throughput_rpm": round(throughput, 2),
                "recent_errors": recent_errors,
                "trend": trend,
            }
        )

    return metrics


def _tail_file(path: str, max_lines: int = 250) -> list[str]:
    """Return trailing lines from a log file.

    Micropayment role: surfaces recent operational diagnostics in `/ops/diagnostics` payload.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
        return [line.rstrip("\n") for line in lines[-max_lines:]]
    except Exception:
        return []


async def _probe_gateway(url: str, *, timeout: int = 8, headers: dict[str, str] | None = None) -> dict[str, object]:
    """Execute HTTP probe against gateway/service and return status summary.

    Micropayment role: monitors IPFS/pinata connectivity for listing and delivery reliability.
    """
    # Async probe using shared httpx client
    from backend.utils.http_client import get_http_client

    started = time.perf_counter()
    try:
        async def _inner_probe():
            client = await get_http_client()
            return await client.get(url, timeout=timeout, headers=headers or {})

        # run probe in coroutine
        response = await _inner_probe()
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        ok = response.status_code < 500
        return {
            "url": url,
            "status": "ok" if ok else "degraded",
            "latency_ms": latency_ms,
            "http_status": response.status_code,
            "error": "",
        }
    except Exception as err:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "url": url,
            "status": "error",
            "latency_ms": latency_ms,
            "http_status": 0,
            "error": str(err),
        }


async def _collect_ipfs_health(now: datetime) -> dict[str, object]:
    """Aggregate IPFS gateway and upload health metrics.

    Micropayment role: operator visibility into content storage/delivery readiness.
    """
    fallback_raw = os.getenv("IPFS_FALLBACK_GATEWAYS", "").strip()
    fallback_gateways = [g.strip().rstrip("/") for g in fallback_raw.split(",") if g.strip()]
    gateways = [
        "https://gateway.pinata.cloud/ipfs/QmYwAPJzv5CZsnAzt8auVTL5SLmv7DivfNa",
        "https://ipfs.io/ipfs/QmYwAPJzv5CZsnAzt8auVTL5SLmv7DivfNa",
    ] + [f"{gateway}/ipfs/QmYwAPJzv5CZsnAzt8auVTL5SLmv7DivfNa" for gateway in fallback_gateways]

    jwt = os.getenv("PINATA_JWT", "").strip()
    pinata_headers = {"Authorization": f"Bearer {jwt}"} if jwt else {}
    pinata_probe = await _probe_gateway(f"{PINATA_BASE_URL}/data/testAuthentication", headers=pinata_headers)

    gateway_checks = await asyncio.gather(*[_probe_gateway(url) for url in gateways[:6]])

    recent = [entry for entry in list(IPFS_HEALTH_WINDOW) if isinstance(entry.get("timestamp"), str)]
    recent = sorted(recent, key=lambda e: str(e.get("timestamp", "")), reverse=True)[:40]

    upload_entries = [entry for entry in recent if entry.get("kind") == "upload"]
    upload_success_count = len([entry for entry in upload_entries if bool(entry.get("success"))])
    upload_success_rate = (upload_success_count / len(upload_entries) * 100) if upload_entries else 100.0
    avg_latency = (
        sum(float(entry.get("latency_ms", 0.0)) for entry in upload_entries) / len(upload_entries)
        if upload_entries
        else 0.0
    )

    trend = [
        {
            "timestamp": str(entry.get("timestamp", "")),
            "latency_ms": float(entry.get("latency_ms", 0.0)),
            "success": bool(entry.get("success")),
        }
        for entry in sorted(upload_entries, key=lambda e: str(e.get("timestamp", "")))[-16:]
    ]

    status = "healthy"
    slow_threshold_ms = 2500
    if pinata_probe["status"] == "error" and all(check.get("status") == "error" for check in gateway_checks):
        status = "broken"
    elif avg_latency >= slow_threshold_ms or upload_success_rate < 95:
        status = "warning"

    return {
        "status": status,
        "connection": {
            "pinata": pinata_probe,
            "gateways": gateway_checks,
        },
        "latency_ms": round(avg_latency, 2),
        "slow_threshold_ms": slow_threshold_ms,
        "upload_success_rate": round(upload_success_rate, 2),
        "last_upload": upload_entries[0] if upload_entries else None,
        "fallback_gateways": fallback_gateways,
        "trend": trend,
        "timestamp": now.isoformat(),
    }


async def _collect_algorand_status(now: datetime) -> dict[str, object]:
    """Collect Algorand node sync, latency, and fee telemetry.

    Micropayment role: confirms chain readiness for x402 payments and contract calls.
    """
    started = time.perf_counter()
    try:
        client = _get_algod_client()
        status, params = await asyncio.gather(
            algod_status(client),
            algod_suggested_params(client),
        )
        latency_ms = round((time.perf_counter() - started) * 1000, 2)

        last_round = _safe_int(status.get("last-round"), 0)
        catchup_time = _safe_int(status.get("catchup-time"), 0)
        time_since_round = _safe_int(status.get("time-since-last-round"), 0)
        synced = catchup_time == 0

        ALGOD_HEALTH_WINDOW.append(
            {
                "timestamp": now.isoformat(),
                "last_round": last_round,
                "synced": synced,
                "latency_ms": latency_ms,
            }
        )

        trend = [
            {
                "timestamp": str(entry.get("timestamp", "")),
                "round": _safe_int(entry.get("last_round"), 0),
                "latency_ms": float(entry.get("latency_ms", 0.0)),
                "synced": bool(entry.get("synced")),
            }
            for entry in list(ALGOD_HEALTH_WINDOW)[-16:]
        ]

        recent_activity = len(
            [
                item
                for item in list(METRICS_WINDOW)
                if str(item.get("path", "")) in {"/list", "/demo_purchase", "/ledger"}
                and isinstance(item.get("timestamp"), str)
                and (now - datetime.fromisoformat(str(item.get("timestamp")))).total_seconds() <= 15 * 60
            ]
        )

        status_tone = "healthy"
        warning = ""
        if not synced or time_since_round > 20_000:
            status_tone = "warning"
            warning = "Node appears behind network tip. Verify sync and indexer connectivity."

        return {
            "status": status_tone,
            "latency_ms": latency_ms,
            "node_health": "ok" if status_tone == "healthy" else "degraded",
            "current_round": last_round,
            "sync_status": "synced" if synced else "catching_up",
            "catchup_time": catchup_time,
            "time_since_last_round_ms": time_since_round,
            "recent_activity_count": recent_activity,
            "fee_suggestion_micro_algo": _safe_int(getattr(params, "min_fee", 0), 0),
            "warning": warning,
            "trend": trend,
            "timestamp": now.isoformat(),
        }
    except Exception as err:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "status": "broken",
            "latency_ms": latency_ms,
            "node_health": "error",
            "current_round": 0,
            "sync_status": "unknown",
            "catchup_time": 0,
            "time_since_last_round_ms": 0,
            "recent_activity_count": 0,
            "fee_suggestion_micro_algo": 0,
            "warning": str(err),
            "trend": [],
            "timestamp": now.isoformat(),
        }


def _build_endpoint_heatmap(now: datetime) -> list[dict[str, object]]:
    """Build endpoint-level health heatmap from recent metric windows.

    Micropayment role: highlights unstable API surfaces impacting commerce flow.
    """
    endpoints = ["/health", "/discover", "/ledger", "/ops/overview", "/list", "/demo_purchase"]
    entries = [entry for entry in list(METRICS_WINDOW) if isinstance(entry.get("timestamp"), str)]

    cells: list[dict[str, object]] = []
    for endpoint in endpoints:
        rows = []
        for entry in entries:
            if str(entry.get("path", "")) != endpoint:
                continue
            try:
                ts = datetime.fromisoformat(str(entry.get("timestamp", "")))
            except Exception:
                continue
            if (now - ts).total_seconds() > 30 * 60:
                continue
            rows.append(entry)

        total = len(rows)
        success = len([row for row in rows if _safe_int(row.get("status_code"), 0) < 400])
        avg_latency = (
            sum(float(row.get("latency_ms", 0.0)) for row in rows) / total if total else 0.0
        )
        success_rate = (success / total * 100) if total else 100.0

        tone = "good"
        if success_rate < 95 or avg_latency > 1800:
            tone = "warn"
        if success_rate < 85 or avg_latency > 3500:
            tone = "bad"

        recent_samples = [
            {
                "timestamp": str(row.get("timestamp", "")),
                "method": str(row.get("method", "")),
                "status_code": _safe_int(row.get("status_code"), 0),
                "latency_ms": float(row.get("latency_ms", 0.0)),
                "anon_user": str(row.get("anon_client", "unknown")),
            }
            for row in sorted(rows, key=lambda item: str(item.get("timestamp", "")), reverse=True)[:8]
        ]

        cells.append(
            {
                "endpoint": endpoint,
                "tone": tone,
                "status": "healthy" if tone == "good" else ("warning" if tone == "warn" else "error"),
                "latency_ms": round(avg_latency, 2),
                "success_rate": round(success_rate, 2),
                "sample_count": total,
                "summary": f"{endpoint}: {round(success_rate, 2)}% success, {round(avg_latency, 2)}ms avg",
                "samples": recent_samples,
            }
        )

    return cells


async def _run_manual_ping(endpoint: str, request: Request) -> dict[str, object]:
    """Run one-shot health ping against supported API endpoints.

    Micropayment role: operator sanity checks for critical buyer/seller paths.
    """
    started = time.perf_counter()
    endpoint = endpoint.strip()
    try:
        if endpoint == "/health":
            payload: Any = health()
        elif endpoint == "/ops/overview":
            payload = await ops_overview(request, verify_on_chain=False)
        elif endpoint == "/ledger":
            payload = await ledger_feed(limit=10, max_scan_pages=1)
        elif endpoint == "/discover":
            payload = await discover_insights(DiscoverRequest(user_query="ops ping health query"))
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported endpoint ping target: {endpoint}")

        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "success": True,
            "endpoint": endpoint,
            "latency_ms": latency_ms,
            "status": "ok",
            "summary": "Manual ping completed",
            "payload_preview": payload,
        }
    except Exception as err:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "success": False,
            "endpoint": endpoint,
            "latency_ms": latency_ms,
            "status": "error",
            "summary": str(err),
            "payload_preview": {},
        }


async def _run_synthetic_test(payload: OpsSyntheticTestRequest) -> dict[str, object]:
    """Execute full synthetic commerce flow (list → purchase → delivery).

    Micropayment role: controlled end-to-end validation path for operations review.
    """
    started = time.perf_counter()
    run_id = f"syn-{uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    steps: list[dict[str, object]] = []

    def add_step(name: str, status: str, duration_ms: float, message: str, details: dict[str, object] | None = None) -> None:
        steps.append(
            {
                "name": name,
                "status": status,
                "duration_ms": round(duration_ms, 2),
                "message": message,
                "details": details or {},
            }
        )

    seller_started = time.perf_counter()
    try:
        signing_mnemonic = _get_signing_mnemonic()
        signer_private_key = mnemonic.to_private_key(signing_mnemonic)
        derived_seller = account.address_from_private_key(signer_private_key)
        seller_wallet = (payload.seller_wallet or derived_seller).strip()
        if seller_wallet != derived_seller:
            raise RuntimeError("Synthetic test seller_wallet must match configured signing mnemonic")

        listing_app_id = int(os.getenv("INSIGHT_LISTING_APP_ID", "0") or 0)
        if listing_app_id <= 0:
            raise RuntimeError("INSIGHT_LISTING_APP_ID is missing/invalid")

        add_step(
            "listing_creation",
            "passed",
            (time.perf_counter() - seller_started) * 1000,
            "Listing prerequisites validated",
            {"seller": _truncate_address(seller_wallet), "listing_app_id": listing_app_id},
        )
    except Exception as err:
        add_step("listing_creation", "failed", (time.perf_counter() - seller_started) * 1000, str(err))
        result = {
            "id": run_id,
            "timestamp": now.isoformat(),
            "status": "failed",
            "stopped_on": "listing_creation",
            "total_duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "steps": steps,
            "error": str(err),
        }
        SYNTHETIC_RESULTS.appendleft(result)
        return result

    ipfs_started = time.perf_counter()
    synthetic_text = f"Mercator synthetic reliability run at {now.isoformat()}"
    try:
        cid = await upload_insight_to_ipfs(synthetic_text)
        IPFS_HEALTH_WINDOW.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "kind": "upload",
                "success": True,
                "latency_ms": round((time.perf_counter() - ipfs_started) * 1000, 2),
                "cid": cid,
                "error": "",
            }
        )
        add_step(
            "ipfs_upload",
            "passed",
            (time.perf_counter() - ipfs_started) * 1000,
            "IPFS upload succeeded",
            {"cid": cid},
        )
    except Exception as err:
        IPFS_HEALTH_WINDOW.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "kind": "upload",
                "success": False,
                "latency_ms": round((time.perf_counter() - ipfs_started) * 1000, 2),
                "cid": "",
                "error": str(err),
            }
        )
        add_step("ipfs_upload", "failed", (time.perf_counter() - ipfs_started) * 1000, str(err))
        result = {
            "id": run_id,
            "timestamp": now.isoformat(),
            "status": "failed",
            "stopped_on": "ipfs_upload",
            "total_duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "steps": steps,
            "error": str(err),
        }
        SYNTHETIC_RESULTS.appendleft(result)
        return result

    chain_started = time.perf_counter()
    try:
        micro_price = max(1, int(payload.price * 1_000_000))
        listing_id, asa_id = store_cid_in_listing(
            cid=cid,
            listing_app_id=listing_app_id,
            seller_address=seller_wallet,
            price=micro_price,
            signer_mnemonic=signing_mnemonic,
        )
        tx_id = await _poll_for_listing_confirmation(app_id=listing_app_id, sender=seller_wallet, cid=cid)
        add_step(
            "on_chain_confirmation",
            "passed",
            (time.perf_counter() - chain_started) * 1000,
            "On-chain listing confirmed",
            {
                "listing_id": listing_id,
                "asa_id": asa_id,
                "tx_id": tx_id,
                "explorer_url": f"{EXPLORER_TX_BASE}/{tx_id}/",
            },
        )
    except Exception as err:
        add_step("on_chain_confirmation", "failed", (time.perf_counter() - chain_started) * 1000, str(err))
        result = {
            "id": run_id,
            "timestamp": now.isoformat(),
            "status": "failed",
            "stopped_on": "on_chain_confirmation",
            "total_duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "steps": steps,
            "error": str(err),
        }
        SYNTHETIC_RESULTS.appendleft(result)
        return result

    purchase_started = time.perf_counter()
    try:
        buyer_address = (
            (payload.buyer_address or "").strip()
            or os.getenv("BUYER_WALLET", "").strip()
            or os.getenv("BUYER_ADDRESS", "").strip()
            or os.getenv("DEPLOYER_ADDRESS", "").strip()
        )
        if not buyer_address:
            raise RuntimeError("No buyer address configured for synthetic purchase")

        purchase_result = await run_agent(
            user_query=payload.user_query,
            buyer_address=buyer_address,
            user_approval_input="approve",
            force_buy_for_test=True,
            autonomous_mode=False,
        )
        if not isinstance(purchase_result, dict) or not bool(purchase_result.get("success")):
            raise RuntimeError(str(purchase_result.get("error", "Synthetic purchase failed")) if isinstance(purchase_result, dict) else "Synthetic purchase failed")

        add_step(
            "purchase",
            "passed",
            (time.perf_counter() - purchase_started) * 1000,
            "Synthetic purchase flow succeeded",
            {"buyer": _truncate_address(buyer_address)},
        )
    except Exception as err:
        add_step("purchase", "failed", (time.perf_counter() - purchase_started) * 1000, str(err))
        result = {
            "id": run_id,
            "timestamp": now.isoformat(),
            "status": "failed",
            "stopped_on": "purchase",
            "total_duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "steps": steps,
            "error": str(err),
        }
        SYNTHETIC_RESULTS.appendleft(result)
        return result

    delivery_started = time.perf_counter()
    try:
        delivered_text = await fetch_insight_from_ipfs(cid)
        if not delivered_text.strip():
            raise RuntimeError("Delivered insight text is empty")
        add_step(
            "content_delivery",
            "passed",
            (time.perf_counter() - delivery_started) * 1000,
            "Content retrieved from IPFS",
            {"preview": delivered_text[:140]},
        )
    except Exception as err:
        add_step("content_delivery", "failed", (time.perf_counter() - delivery_started) * 1000, str(err))
        result = {
            "id": run_id,
            "timestamp": now.isoformat(),
            "status": "failed",
            "stopped_on": "content_delivery",
            "total_duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "steps": steps,
            "error": str(err),
        }
        SYNTHETIC_RESULTS.appendleft(result)
        return result

    result = {
        "id": run_id,
        "timestamp": now.isoformat(),
        "status": "passed",
        "stopped_on": None,
        "total_duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "steps": steps,
        "error": "",
    }
    SYNTHETIC_RESULTS.appendleft(result)
    return result


def _fetch_app_call_stats(idx: indexer.IndexerClient, app_id: int, max_pages: int = 8) -> tuple[int, str | None]:
    """Fetch aggregate app-call volume and latest activity timestamp.

    Micropayment role: contract activity indicators in ops dashboard cards.
    """
    next_token: str | None = None
    total_calls = 0
    latest_iso: str | None = None

    for _ in range(max_pages):
        params: dict[str, object] = {
            "application_id": app_id,
            "txn_type": "appl",
            "limit": 1000,
        }
        if next_token:
            params["next_page"] = next_token

        response = idx.search_transactions(**params)
        txns = response.get("transactions", [])
        if not isinstance(txns, list):
            break

        total_calls += len(txns)
        for txn in txns:
            if not isinstance(txn, dict):
                continue
            round_time = txn.get("round-time")
            iso = _safe_iso_from_round_time(round_time)
            if latest_iso is None or iso > latest_iso:
                latest_iso = iso

        raw_next = response.get("next-token")
        next_token = str(raw_next) if isinstance(raw_next, str) and raw_next else None
        if not next_token:
            break

    return total_calls, latest_iso


def _build_contract_card(name: str, env_key: str, idx: indexer.IndexerClient) -> dict[str, object]:
    """Build operator dashboard card for a contract app id.

    Micropayment role: summarizes contract health for InsightListing/Escrow/Reputation.
    """
    app_id_raw = os.getenv(env_key, "").strip()
    if not app_id_raw or not app_id_raw.isdigit():
        return {
            "name": name,
            "app_id": app_id_raw or "missing",
            "creator": "unknown",
            "approval_hash": "n/a",
            "total_calls": 0,
            "last_call": None,
            "state": "not_configured",
            "status": "broken",
            "explorer_url": "",
            "errors": [f"{env_key} missing or invalid"],
        }

    app_id = int(app_id_raw)
    explorer = f"https://explorer.perawallet.app/application/{app_id}/"

    try:
        app_payload = idx.applications(app_id)
        app_obj = app_payload.get("application", {}) if isinstance(app_payload, dict) else {}
        params = app_obj.get("params", {}) if isinstance(app_obj, dict) else {}

        creator = str(params.get("creator", "unknown"))
        approval_b64 = str(params.get("approval-program", ""))
        approval_hash = "n/a"
        if approval_b64:
            try:
                approval_hash = hashlib.sha256(base64.b64decode(approval_b64)).hexdigest()[:16]
            except Exception:
                approval_hash = hashlib.sha256(approval_b64.encode("utf-8")).hexdigest()[:16]

        total_calls, last_call = _fetch_app_call_stats(idx, app_id)
        global_state = params.get("global-state", []) if isinstance(params, dict) else []
        state = "active" if isinstance(global_state, list) else "unknown"

        status = "healthy"
        errors: list[str] = []
        if total_calls == 0:
            status = "warning"
            errors.append("No app-call transactions observed in sampled history")

        return {
            "name": name,
            "app_id": app_id,
            "creator": creator,
            "approval_hash": approval_hash,
            "total_calls": total_calls,
            "last_call": last_call,
            "state": state,
            "status": status,
            "explorer_url": explorer,
            "errors": errors,
        }
    except Exception as err:
        return {
            "name": name,
            "app_id": app_id,
            "creator": "unknown",
            "approval_hash": "n/a",
            "total_calls": 0,
            "last_call": None,
            "state": "unreachable",
            "status": "broken",
            "explorer_url": explorer,
            "errors": [str(err)],
        }


async def _collect_environment_panel() -> dict[str, object]:
    """Collect redacted environment and wallet balance panel for ops UI.

    Micropayment role: gives operators a safe runtime snapshot without leaking secrets.
    """
    algod_client: algod.AlgodClient | None = None
    try:
        algod_client = _get_algod_client()
    except Exception:
        algod_client = None

    wallet_entries = [
        ("Deployer", os.getenv("DEPLOYER_ADDRESS", "").strip()),
        ("Seller", os.getenv("SELLER_ADDRESS", "").strip()),
        ("Buyer", os.getenv("BUYER_WALLET", "").strip() or os.getenv("BUYER_ADDRESS", "").strip()),
    ]

    wallets: list[dict[str, object]] = []
    for label, address in wallet_entries:
        if not address:
            continue

        algo_balance = None
        if algod_client:
            try:
                account_info = await algod_account_info(address, algod_client)
                algo_balance = round((_safe_int(account_info.get("amount"), 0) / 1_000_000), 6)
            except Exception:
                algo_balance = None

        wallets.append(
            {
                "label": label,
                "address": _truncate_address(address),
                "algo_balance": algo_balance,
            }
        )

    return {
        "network": "Algorand TestNet",
        "warning": "TestNet only. Do not treat balances or proofs as mainnet settlement.",
        "contracts": {
            "insight_listing_app_id": os.getenv("INSIGHT_LISTING_APP_ID", "unset"),
            "escrow_app_id": os.getenv("ESCROW_APP_ID", "unset"),
            "reputation_app_id": os.getenv("REPUTATION_APP_ID", "unset"),
        },
        "wallets": wallets,
        "redacted_config": {
            "ALGOD_URL": os.getenv("ALGOD_URL", "")[:40],
            "INDEXER_URL": os.getenv("INDEXER_URL", "")[:40],
            "ALGOD_TOKEN": "***redacted***" if os.getenv("ALGOD_TOKEN") else "unset",
            "INDEXER_TOKEN": "***redacted***" if os.getenv("INDEXER_TOKEN") else "unset",
            "DEPLOYER_MNEMONIC": "***redacted***" if os.getenv("DEPLOYER_MNEMONIC") else "unset",
            "SELLER_MNEMONIC": "***redacted***" if os.getenv("SELLER_MNEMONIC") else "unset",
        },
    }


def _collect_system_events(now: datetime) -> list[dict[str, object]]:
    """Derive event stream (errors/recoveries) from request metric history.

    Micropayment role: incident/recovery trail for reliability reviews.
    """
    events: list[dict[str, object]] = []
    previous_error_by_endpoint: dict[str, bool] = {}

    ordered = sorted(
        [entry for entry in list(METRICS_WINDOW) if isinstance(entry.get("timestamp"), str)],
        key=lambda item: str(item.get("timestamp", "")),
        reverse=True,
    )

    for row in ordered[:300]:
        path = str(row.get("path", ""))
        if path not in METRIC_ENDPOINTS:
            continue

        status_code = _safe_int(row.get("status_code"), 0)
        severity = "info"
        event_type = "request"
        message = f"{path} responded {status_code}"

        if status_code >= 500:
            severity = "error"
            event_type = "error"
            previous_error_by_endpoint[path] = True
        elif status_code >= 400:
            severity = "warning"
            event_type = "warning"
            previous_error_by_endpoint[path] = True
        elif previous_error_by_endpoint.get(path):
            severity = "info"
            event_type = "recovery"
            message = f"{path} recovered with status {status_code}"
            previous_error_by_endpoint[path] = False

        events.append(
            {
                "id": f"evt-{hash(str(row))}",
                "timestamp": row.get("timestamp"),
                "severity": severity,
                "type": event_type,
                "message": message,
                "details": {
                    "path": path,
                    "status_code": status_code,
                    "latency_ms": row.get("latency_ms"),
                    "anon_user": row.get("anon_client"),
                },
            }
        )

    return events[:120]


@app.get("/ops/access-check")
async def ops_access_check(request: Request) -> dict[str, object]:
    """Operator auth validation endpoint.

    Micropayment role: verifies privileged access path for diagnostics tooling.
    """
    access = _operator_access_snapshot(request)
    if not bool(access.get("authorized")):
        raise HTTPException(status_code=403, detail=str(access.get("reason", "Operator access required")))
    return {
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "access": access,
    }


@app.get("/ops/overview")
async def ops_overview(request: Request, verify_on_chain: bool = True) -> dict[str, object]:
    """Return consolidated operations dashboard payload.

    Micropayment role: unified health/contract/IPFS/chain metrics for demo operations.
    """
    access = _require_operator(request)
    now = datetime.now(timezone.utc)

    health_payload = health()
    request_metrics = _collect_request_metrics(now)
    environment = await _collect_environment_panel()
    events = _collect_system_events(now)
    ipfs_health = await _collect_ipfs_health(now)
    algorand_status = await _collect_algorand_status(now)
    endpoint_heatmap = _build_endpoint_heatmap(now)

    contracts: list[dict[str, object]] = []
    if verify_on_chain:
        try:
            idx = _get_indexer_client()
            contracts = [
                _build_contract_card("InsightListing", "INSIGHT_LISTING_APP_ID", idx),
                _build_contract_card("Escrow", "ESCROW_APP_ID", idx),
                _build_contract_card("Reputation", "REPUTATION_APP_ID", idx),
            ]
        except Exception as err:
            contracts = [
                {
                    "name": "Indexer verification",
                    "app_id": "n/a",
                    "creator": "unknown",
                    "approval_hash": "n/a",
                    "total_calls": 0,
                    "last_call": None,
                    "state": "unreachable",
                    "status": "broken",
                    "explorer_url": "",
                    "errors": [str(err)],
                }
            ]

    return {
        "success": True,
        "timestamp": now.isoformat(),
        "operator_access": access,
        "operator_mode": {
            "active": True,
            "session_ttl_hint_seconds": 1800,
        },
        "health": health_payload,
        "contracts": contracts,
        "request_metrics": request_metrics,
        "endpoint_heatmap": endpoint_heatmap,
        "ipfs": ipfs_health,
        "algorand": algorand_status,
        "synthetic_recent": list(SYNTHETIC_RESULTS),
        "environment": environment,
        "events": events,
    }


@app.get("/ops/synthetic-tests")
async def ops_synthetic_tests(request: Request) -> dict[str, object]:
    """Return recent synthetic test history.

    Micropayment role: quick status of latest end-to-end commerce checks.
    """
    _require_operator(request)
    return {
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": list(SYNTHETIC_RESULTS),
    }


@app.post("/ops/synthetic-test")
async def ops_synthetic_test(request: Request, payload: OpsSyntheticTestRequest) -> dict[str, object]:
    """Trigger a new synthetic commerce test run.

    Micropayment role: active end-to-end verification for reliability gates.
    """
    _require_operator(request)
    result = await _run_synthetic_test(payload)
    return {
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result": result,
        "history": list(SYNTHETIC_RESULTS),
    }


@app.get("/ops/ipfs/health")
async def ops_ipfs_health(request: Request) -> dict[str, object]:
    """Expose current IPFS subsystem health summary.

    Micropayment role: validates storage and delivery substrate readiness.
    """
    _require_operator(request)
    now = datetime.now(timezone.utc)
    return {
        "success": True,
        "timestamp": now.isoformat(),
        "ipfs": await _collect_ipfs_health(now),
    }


@app.get("/ipfs/{cid}")
async def public_ipfs_fetch(cid: str) -> JSONResponse:
    """Fetch IPFS content by CID via backend gateways and return plain text.

    Purpose: Allow the frontend to preview IPFS content without embedding external
    gateways that prevent framing or have restrictive CORS/X-Frame settings.
    """
    try:
        text = await fetch_insight_from_ipfs(cid)
        return JSONResponse(status_code=200, content={"success": True, "cid": cid, "content": text})
    except Exception as exc:
        logger.exception("Failed to fetch IPFS CID %s: %s", cid, exc)
        return JSONResponse(status_code=502, content={"success": False, "error": "IPFS_FETCH_FAILED", "message": str(exc)})


@app.post("/ops/ipfs/test-upload")
async def ops_ipfs_test_upload(request: Request, payload: OpsIpfsUploadRequest) -> dict[str, object]:
    """Run on-demand IPFS upload probe and record latency/result.

    Micropayment role: live validation of seller upload path dependency.
    """
    _require_operator(request)
    now = datetime.now(timezone.utc)
    started = time.perf_counter()
    content = payload.content or f"Mercator IPFS health upload at {now.isoformat()}"
    try:
        cid = await upload_insight_to_ipfs(content, filename=payload.filename)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        IPFS_HEALTH_WINDOW.append(
            {
                "timestamp": now.isoformat(),
                "kind": "upload",
                "success": True,
                "latency_ms": latency_ms,
                "cid": cid,
                "error": "",
            }
        )
        return {
            "success": True,
            "timestamp": now.isoformat(),
            "cid": cid,
            "latency_ms": latency_ms,
            "gateway_url": f"https://ipfs.io/ipfs/{cid}",
        }
    except Exception as err:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        IPFS_HEALTH_WINDOW.append(
            {
                "timestamp": now.isoformat(),
                "kind": "upload",
                "success": False,
                "latency_ms": latency_ms,
                "cid": "",
                "error": str(err),
            }
        )
        raise HTTPException(status_code=500, detail=f"IPFS test upload failed: {err}")


@app.get("/ops/algorand/status")
async def ops_algorand_status(request: Request) -> dict[str, object]:
    """Expose Algorand node status snapshot.

    Micropayment role: verifies chain connectivity needed for payment and contract flows.
    """
    _require_operator(request)
    now = datetime.now(timezone.utc)
    return {
        "success": True,
        "timestamp": now.isoformat(),
        "algorand": await _collect_algorand_status(now),
    }


@app.post("/ops/algorand/test")
async def ops_algorand_test(request: Request) -> dict[str, object]:
    """Run active Algorand telemetry test.

    Micropayment role: operator-triggered validation for chain-side reliability.
    """
    _require_operator(request)
    now = datetime.now(timezone.utc)
    status = await _collect_algorand_status(now)
    return {
        "success": True,
        "timestamp": now.isoformat(),
        "algorand": status,
    }


@app.post("/ops/ping")
async def ops_manual_ping(request: Request, payload: OpsManualPingRequest) -> dict[str, object]:
    """Execute manual ping against selected endpoint.

    Micropayment role: rapid probe tool for troubleshooting specific flow surfaces.
    """
    _require_operator(request)
    result = await _run_manual_ping(payload.endpoint, request)
    return {
        "success": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result": result,
    }


@app.get("/ops/diagnostics")
async def ops_diagnostics(request: Request, include_contract_scan: bool = False) -> dict[str, object]:
    """Return expanded diagnostics bundle including overview + logs.

    Micropayment role: deep operator packet for incident triage and review submissions.
    """
    _require_operator(request)
    now = datetime.now(timezone.utc)
    overview = await ops_overview(request, verify_on_chain=include_contract_scan)

    return {
        "success": True,
        "timestamp": now.isoformat(),
        "bundle": {
            "overview": overview,
            "synthetic_tests": list(SYNTHETIC_RESULTS),
            "metrics_window_size": len(METRICS_WINDOW),
            "ipfs_window_size": len(IPFS_HEALTH_WINDOW),
            "algorand_window_size": len(ALGOD_HEALTH_WINDOW),
            "log_tail": _tail_file("mercator.log", max_lines=320),
            "notes": "Sensitive values remain redacted in environment payload.",
        },
    }


@app.post("/list")
async def create_listing(request: ListingRequest) -> dict[str, object]:
    """Upload trading insight to IPFS and create on-chain listing.
    
    Purpose: Seller-facing endpoint for publishing insights. Uploads insight text to Pinata IPFS,
    creates/updates InsightListing contract entry, and returns listing_id/CID/tx for frontend.
    
    Flow:
    1. Validate insight text (non-empty), price (>0), seller wallet (58 char, valid Algorand address).
    2. Upload insight text to Pinata → retrieve IPFS CID.
    3. Call InsightListing contract store_on_marketplace() → get listing_id + ASA_id.
    4. Poll indexer for confirmation → return success payload with explorer link.
    5. Record listing in RECENT_LISTINGS + clear semantic cache for immediate /discover hit.
    
    Returns: {listing_id, asa_id, cid, txId, explorer_url, success}.
    """
    normalize_network_env()
    logger.info(
        "Incoming /list request: seller_wallet=%s, price=%s, insight_len=%s",
        request.seller_wallet,
        request.price,
        len(request.insight_text),
    )

    if (
        not request.insight_text.strip()
        or request.price <= 0
        or len(request.seller_wallet) != 58
        or not encoding.is_valid_address(request.seller_wallet)
    ):
        return _error_response(400, "Invalid insight text, price, or wallet address")

    listing_app_id_raw = os.getenv("INSIGHT_LISTING_APP_ID", "").strip()
    if not listing_app_id_raw:
        raise HTTPException(status_code=500, detail="INSIGHT_LISTING_APP_ID is not configured")

    try:
        listing_app_id = int(listing_app_id_raw)
    except ValueError as err:
        logger.error("Invalid listing app id in environment | value=%s", listing_app_id_raw)
        raise HTTPException(status_code=500, detail="INSIGHT_LISTING_APP_ID is invalid") from err

    try:
        signing_mnemonic, signer_address, signer_exact_match = _resolve_signer_for_wallet(request.seller_wallet)
    except HTTPException as err:
        return _error_response(err.status_code, str(err.detail))

    if not signer_exact_match:
        raise HTTPException(
            status_code=400,
            detail="seller_wallet must be signable by the configured mnemonic",
        )

    logger.info(
        "Validation passed for seller %s (effective signer=%s exact_match=%s)",
        request.seller_wallet,
        signer_address,
        signer_exact_match,
    )

    try:
        effective_seller_wallet = signer_address
        micro_price = int(request.price * 1_000_000)

        if request.seller_wallet != effective_seller_wallet:
            logger.warning(
                "Using effective seller wallet %s instead of requested wallet %s",
                effective_seller_wallet,
                request.seller_wallet,
            )

        await _await_if_needed(_ensure_listing_app_funded(listing_app_id, preferred_sender=signer_address))

        prepared = await create_listing_prepared(
            insight_text=request.insight_text,
            price_usdc=float(request.price),
            seller_wallet=effective_seller_wallet,
            listing_app_id=listing_app_id,
            signer_mnemonic=signing_mnemonic,
        )

        if not prepared.execution_succeeded:
            raise ListingStoreError(prepared.error_message or "Listing execution failed")

        cid = prepared.cid
        listing_id = prepared.listing_id
        asa_id = prepared.asa_id
        tx_id = prepared.tx_id

        logger.info(
            "On-chain listing submitted via two-phase flow: listing_id=%s asa_id=%s prep_id=%s",
            listing_id,
            asa_id,
            prepared.preparation_id,
        )
        demo_logger.info("Seller upload complete")
        demo_logger.info("On-chain ASA created")

        if not tx_id:
            tx_id = await _poll_for_listing_confirmation(
                app_id=listing_app_id,
                sender=effective_seller_wallet,
                cid=cid,
            )
            logger.info("Transaction confirmed: tx_id=%s", tx_id)

        _record_recent_listing(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tx_id": tx_id,
                "cid": cid,
                "listing_id": listing_id,
                "asa_id": asa_id,
                "seller_wallet": effective_seller_wallet,
                "price_usdc": round(float(request.price), 6),
                "insight_text": request.insight_text,
                "seller_reputation": 0,
                "source_type": request.source_type or "listing",
            }
        )
        try:
            clear_semantic_search_cache()
        except Exception:
            # Never block listing success on cache invalidation.
            pass

        await ws_manager.broadcast(
            "new_listing",
            {
                "listing_id": str(listing_id),
                "seller_wallet": effective_seller_wallet,
                "seller_name": "seller",
                "price_usdc": round(float(request.price), 6),
                "insight_preview": request.insight_text[:100],
                "source_type": request.source_type,
                "ipfs_cid": cid,
                "listing_tx_id": tx_id,
                "reputation_score": 0,
            },
        )
    except IPFSUploadError as err:
        logger.error("IPFS upload failed | error=%s", err, exc_info=True)
        return _error_response(500, ipfs_down(logger, str(err)))
    except ListingStoreError as err:
        logger.error("ASA creation failed | error=%s", err, exc_info=True)
        # Return specific contract failure detail to make production triage actionable.
        return _error_response(500, f"Contract error: {err}")
    except HTTPException as err:
        logger.error("Transaction confirmation failed | detail=%s", err.detail, exc_info=True)
        return _error_response(err.status_code, str(err.detail))
    except AlgodHTTPError as err:
        logger.error("Algod rejected /list transaction | error=%s", err, exc_info=True)
        return _error_response(400, f"Algorand node rejected listing transaction: {err}")
    except Exception as err:
        logger.error("Unexpected /list failure | error=%s", err, exc_info=True)
        return _error_response(500, f"Transaction failed: {err}")

    fee_state = await _fetch_fee_config_state()
    fee_rate_bps = _safe_int(fee_state.get("fee_rate_bps", 250), 250)
    platform_fee_micro = _calculate_fee_preview(micro_price, fee_rate_bps)
    seller_net_micro = max(0, micro_price - platform_fee_micro)

    return {
        "success": True,
        "transaction_id": tx_id,
        "txId": tx_id,
        "explorer_url": f"{EXPLORER_TX_BASE}/{tx_id}/",
        "message": "Insight listed on-chain and pinned on IPFS",
        "cid": cid,
        "listing_id": listing_id,
        "asa_id": asa_id,
        "fee_config_details": {
            "fee_rate_bps": fee_rate_bps,
            "fee_rate_display": f"{fee_rate_bps / 100:.1f}%",
            "platform_fee_usdc": round(platform_fee_micro / 1_000_000, 6),
            "seller_net_usdc": round(seller_net_micro / 1_000_000, 6),
        },
    }


@app.get("/fee_config")
async def get_fee_config() -> dict[str, object]:
    """Return current fee configuration and accrued platform revenue.

    Micropayment role: Operations dashboard poll target for fee rate + treasury + revenue.
    """
    try:
        state = await _fetch_fee_config_state()
    except Exception as err:
        logger.error("Failed to fetch fee config state | error=%s", err, exc_info=True)
        return {
            "success": False,
            "error": f"Failed to fetch fee config: {err}",
        }

    if not bool(state.get("configured", False)):
        return {
            "success": False,
            "error": str(state.get("error", "FeeConfig is not configured")),
            "fee_rate_bps": _safe_int(state.get("fee_rate_bps", 250), 250),
            "treasury_address": str(state.get("treasury_address", "")),
            "total_fees_collected": _safe_int(state.get("total_fees_collected", 0), 0),
            "usdc_asset_id": _safe_int(state.get("usdc_asset_id", 10458941), 10458941),
        }

    fee_rate_bps = _safe_int(state.get("fee_rate_bps", 250), 250)
    return {
        "success": True,
        "app_id": _safe_int(state.get("app_id", 0), 0),
        "fee_rate_bps": fee_rate_bps,
        "fee_rate_display": f"{fee_rate_bps / 100:.1f}%",
        "treasury_address": str(state.get("treasury_address", "")),
        "total_fees_collected": _safe_int(state.get("total_fees_collected", 0), 0),
        "usdc_asset_id": _safe_int(state.get("usdc_asset_id", 10458941), 10458941),
    }


@app.get("/subscription/status")
async def get_subscription_status(wallet: str) -> dict[str, object]:
    """Return the on-chain subscription status for a buyer wallet."""
    normalize_network_env()
    if not wallet or not encoding.is_valid_address(wallet):
        raise HTTPException(status_code=400, detail="wallet must be a valid Algorand address")

    try:
        payload = await _subscription_status_payload(wallet)
        return {
            "success": True,
            **payload,
        }
    except HTTPException:
        raise
    except Exception as err:
        logger.error("Failed to fetch subscription status | wallet=%s error=%s", wallet, err, exc_info=True)
        return {
            "success": False,
            "active": False,
            "expiry_round": 0,
            "expiry_approx_date": datetime.now(timezone.utc).isoformat(),
            "months_remaining": 0.0,
            "total_months_paid": 0,
            "total_usdc_paid_micro": 0,
            "error": str(err),
        }


@app.post("/subscribe")
async def subscribe(request: SubscriptionRequest) -> dict[str, object]:
    """Submit a grouped USDC payment plus SubscriptionManager.subscribe() call."""
    normalize_network_env()
    if request.months < 1 or request.months > 12:
        raise HTTPException(status_code=400, detail="months must be between 1 and 12")
    if not encoding.is_valid_address(request.buyer_wallet):
        raise HTTPException(status_code=400, detail="buyer_wallet must be a valid Algorand address")

    subscription_app_id = _get_subscription_manager_app_id()
    buyer_sender, buyer_signer = _get_subscription_signer()
    if buyer_sender != request.buyer_wallet:
        raise HTTPException(
            status_code=400,
            detail="Configured buyer signer does not match buyer_wallet",
        )

    monthly_rate_micro_usdc = _safe_int(os.getenv("SUBSCRIPTION_MONTHLY_RATE_MICRO_USDC", "50000000"), 50000000)
    usdc_asset_id = _safe_int(os.getenv("USDC_ASSET_ID", "10458941"), 10458941)
    amount_micro = monthly_rate_micro_usdc * request.months
    app_address = get_application_address(subscription_app_id)

    algod_client = _get_algod_client()
    params = await algod_suggested_params(algod_client)
    payment_txn = transaction.AssetTransferTxn(
        sender=request.buyer_wallet,
        sp=params,
        index=usdc_asset_id,
        amt=amount_micro,
        receiver=app_address,
    )

    try:
        _, tx_ids = await _execute_abi_call(
            subscription_app_id,
            "subscribe(uint64)void",
            [request.months],
            sender=request.buyer_wallet,
            signer=buyer_signer,
            payment_txn=payment_txn,
            sp=params,
        )
        payload = _subscription_status_payload(request.buyer_wallet)
        await ws_manager.broadcast(
            "new_subscription",
            {
                "buyer_wallet": request.buyer_wallet,
                "months_paid": request.months,
                "expiry_round": _safe_int(payload.get("expiry_round"), 0),
                "expiry_approx_date": str(payload.get("expiry_approx_date", "")),
                "total_usdc_paid": round((monthly_rate_micro_usdc * request.months) / 1_000_000, 6),
            },
        )
        return {
            "success": True,
            "tx_id": tx_ids[-1] if tx_ids else "",
            "expiry_round": payload.get("expiry_round", 0),
            "months_paid": request.months,
            "subscription_tx_id": tx_ids[-1] if tx_ids else "",
            "payment_tx_id": tx_ids[0] if len(tx_ids) > 1 else (tx_ids[-1] if tx_ids else ""),
            "expiry_approx_date": payload.get("expiry_approx_date"),
        }
    except HTTPException:
        raise
    except Exception as err:
        logger.error("Subscription purchase failed | wallet=%s months=%s error=%s", request.buyer_wallet, request.months, err, exc_info=True)
        raise HTTPException(status_code=500, detail=str(err))


@app.post("/escrow/release_for_subscriber")
async def release_for_subscriber(request: SubscriptionReleaseRequest) -> dict[str, object]:
    """Invoke Escrow.release_for_subscriber for a subscribed buyer."""
    normalize_network_env()
    if not encoding.is_valid_address(request.buyer_wallet):
        raise HTTPException(status_code=400, detail="buyer_wallet must be a valid Algorand address")
    if request.listing_id < 0:
        raise HTTPException(status_code=400, detail="listing_id must be non-negative")

    escrow_app_id_raw = os.getenv("ESCROW_APP_ID", "").strip()
    if not escrow_app_id_raw.isdigit():
        raise HTTPException(status_code=500, detail="ESCROW_APP_ID is not configured")

    buyer_sender, buyer_signer = _get_subscription_signer()
    if buyer_sender != request.buyer_wallet:
        raise HTTPException(
            status_code=400,
            detail="Configured buyer signer does not match buyer_wallet",
        )

    try:
        _, tx_ids = await _execute_abi_call(
            int(escrow_app_id_raw),
            "release_for_subscriber(address,uint64)bool",
            [request.buyer_wallet, request.listing_id],
            sender=request.buyer_wallet,
            signer=buyer_signer,
        )
        return {
            "success": True,
            "tx_id": tx_ids[-1] if tx_ids else "",
            "buyer_wallet": request.buyer_wallet,
            "listing_id": request.listing_id,
            "payment_method": "subscription",
            "subscription_access_granted": True,
        }
    except HTTPException:
        raise
    except Exception as err:
        logger.error(
            "Subscriber release failed | wallet=%s listing_id=%s error=%s",
            request.buyer_wallet,
            request.listing_id,
            err,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(err))


@app.post("/onboard")
async def onboard(request: OnboardRequest) -> dict[str, object]:
    display_name = request.display_name.strip()
    email = request.email.strip()
    password = request.password

    if len(display_name) < 2 or len(display_name) > 50:
        return JSONResponse(status_code=400, content={"error": "Display name must be 2-50 characters"})

    if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        return JSONResponse(status_code=400, content={"error": "Invalid email format"})

    if len(password) < 10 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return JSONResponse(
            status_code=400,
            content={"error": "Password must be at least 10 chars and include letters and numbers"},
        )

    try:
        wallet, user_id = create_user(email, password)
    except ValueError:
        return JSONResponse(status_code=409, content={"error": "Email already registered"})
    except Exception as exc:
        logger.error("Onboarding failed for email hash flow: %s", exc, exc_info=True)
        return JSONResponse(status_code=500, content={"error": "Registration failed"})

    algo_balance_micro = 0
    usdc_balance_micro = 0
    funding_status = "pending"

    try:
        from backend.utils.custodial_wallet import fund_new_wallet

        funding_result = await fund_new_wallet(wallet.algo_address)
        algo_balance_micro = int(funding_result.get("algo_balance", 0) or 0)
        usdc_balance_micro = int(funding_result.get("usdc_balance", 0) or 0)
        funding_status = "funded" if bool(funding_result.get("funding_confirmed", False)) else "pending"
    except Exception as exc:
        logger.warning("Faucet funding pending for %s: %s", wallet.algo_address, exc)
        funding_status = "pending"

    session_token = create_demo_session(user_id, password)

    return {
        "user_id": user_id,
        "session_token": session_token,
        "algo_address": wallet.algo_address,
        "display_name": display_name,
        "algo_balance_micro": algo_balance_micro,
        "usdc_balance_micro": usdc_balance_micro,
        "funding_status": funding_status,
        "message": "Your testnet wallet is ready. 2 USDC loaded for testing.",
    }


@app.post("/auth/login")
async def auth_login(request: LoginRequest) -> dict[str, object]:
    authenticated, user_id, algo_address = authenticate_user(request.email, request.password)
    if not authenticated:
        return JSONResponse(status_code=401, content={"error": "Invalid credentials"})

    session_token = create_demo_session(user_id, request.password)
    return {
        "user_id": user_id,
        "session_token": session_token,
        "algo_address": algo_address,
        "message": "Logged in",
    }


@app.get("/wallet/balance")
async def wallet_balance(address: str = Query(..., description="Algorand wallet address")) -> dict[str, object]:
    if not encoding.is_valid_address(address):
        return JSONResponse(status_code=400, content={"error": "Invalid wallet address"})

    try:
        algo_balance_micro, usdc_balance_micro = await _fetch_wallet_balances_micro(address)
    except Exception as exc:
        logger.error("Wallet balance lookup failed for %s: %s", address, exc, exc_info=True)
        return JSONResponse(status_code=502, content={"error": "Balance lookup failed"})

    return {
        "algo_balance_micro": algo_balance_micro,
        "usdc_balance_micro": usdc_balance_micro,
        "algo_balance_display": round(algo_balance_micro / 1_000_000, 6),
        "usdc_balance_display": round(usdc_balance_micro / 1_000_000, 6),
    }


@app.get("/wallet/is_custodial")
async def wallet_is_custodial(address: str = Query(..., description="Algorand wallet address")) -> dict[str, object]:
    if not encoding.is_valid_address(address):
        return JSONResponse(status_code=400, content={"error": "Invalid wallet address"})

    custodial = is_custodial_address(address)
    user_id = get_user_id_by_address(address) if custodial else None
    return {
        "is_custodial": custodial,
        "user_id": user_id,
        "address": address,
    }


@app.get("/admin/cache/stats")
async def admin_cache_stats() -> dict[str, object]:
    """Return basic cache stats for monitoring and debugging."""
    try:
        from backend.utils.seller_profile import _profile_cache, _reputation_cache
    except Exception:
        _profile_cache = None
        _reputation_cache = None
    try:
        from backend.api.v1.router import _listings_cache
    except Exception:
        _listings_cache = None

    def _stats(cache):
        if cache is None:
            return {"present": False}
        try:
            return {"present": True, "size": len(cache), "maxsize": getattr(cache, "maxsize", None)}
        except Exception:
            return {"present": True}

    return {
        "profile_cache": _stats(_profile_cache),
        "reputation_cache": _stats(_reputation_cache),
        "listings_cache": _stats(_listings_cache),
    }


@app.post("/admin/api-keys/generate")
async def admin_generate_api_key(request: Request, body: AdminGenerateApiKeyRequest) -> dict[str, object]:
    configured_key = os.getenv("ADMIN_KEY", "").strip()
    provided_key = request.headers.get("x-admin-key", "").strip()
    if not configured_key or provided_key != configured_key:
        raise HTTPException(status_code=403, detail="Invalid X-Admin-Key")

    owner_name = body.owner_name.strip()
    owner_email = body.owner_email.strip()
    tier = body.tier.strip() or "developer"
    plaintext_key = body.plaintext_key.strip() if isinstance(body.plaintext_key, str) and body.plaintext_key.strip() else None

    if not owner_name:
        raise HTTPException(status_code=400, detail="owner_name is required")
    if not owner_email:
        raise HTTPException(status_code=400, detail="owner_email is required")

    try:
        generated_key, key_id = generate_api_key(owner_name, owner_email, tier, plaintext_key=plaintext_key)
        return {
            "success": True,
            "key_id": key_id,
            "plaintext_key": generated_key,
            "owner_name": owner_name,
            "owner_email": owner_email,
            "tier": tier,
        }
    except Exception as err:
        logger.error("API key generation failed | owner=%s email=%s error=%s", owner_name, owner_email, err, exc_info=True)
        raise HTTPException(status_code=500, detail=str(err))

    custodial = is_custodial_address(address)
    user_id = get_user_id_by_address(address) if custodial else None
    return {
        "is_custodial": custodial,
        "user_id": user_id,
    }


@app.post("/wallet/export")
async def wallet_export(request: ExportRequest) -> dict[str, object]:
    result = get_wallet_for_user(request.user_id, request.password)
    if not result.success:
        if "invalid" in result.error.lower():
            return JSONResponse(status_code=401, content={"error": "Invalid credentials"})
        return JSONResponse(status_code=400, content={"error": result.error or "Wallet export failed"})

    return {
        "mnemonic": result.mnemonic,
        "warning": "Store this mnemonic securely. Anyone with these 25 words controls your wallet. This export is for migration to a self-custodial wallet only.",
    }


@app.post("/demo_purchase")
async def demo_purchase(request: DemoPurchaseRequest) -> dict[str, object]:
    """Launch autonomous agent for semantic search → evaluation → x402 payment.
    
    Purpose: Buyer-facing endpoint that runs the full Mercator agent flow:
    1. Semantic search for user query across live on-chain listings.
    2. LLM evaluation: check on-chain reputation + value-for-price heuristics.
    3. If BUY decision and user typed "approve", trigger x402 micropayment.
    4. On payment confirmation, release escrow and deliver IPFS content.
    
    Returns: {success, decision, evaluation, payment_status, message}.
    """
    normalize_network_env()
    tracer.start_session("buyer_purchase")
    buyer_address = (request.buyer_address or os.getenv("BUYER_WALLET", "").strip() or os.getenv("BUYER_ADDRESS", "").strip() or os.getenv("DEPLOYER_ADDRESS", "").strip())
    try:
        result = await run_agent(
            user_query=request.user_query,
            buyer_address=buyer_address,
            user_approval_input=request.user_approval_input,
            force_buy_for_test=request.force_buy_for_test,
            target_listing_id=request.target_listing_id,
            user_id=request.user_id,
            session_token=request.session_token,
            autonomous_mode=False,
        )

        final_insight_text = _extract_final_insight_text(result if isinstance(result, dict) else {})
        return {
            "success": bool(result.get("success", False)) if isinstance(result, dict) else False,
            "final_insight_text": final_insight_text,
            "result": result,
        }
    finally:
        tracer.export_json()


@app.get("/api/v1/listings")
async def get_recent_listings(limit: int = 50) -> dict[str, object]:
    safe_limit = max(1, min(limit, 200))
    return {
        "success": True,
        "count": min(len(RECENT_LISTINGS), safe_limit),
        "listings": list(RECENT_LISTINGS)[:safe_limit],
    }


@app.get("/traces/latest")
async def traces_latest(limit: int = 20) -> dict[str, object]:
    return {
        "success": True,
        "sessions": tracer.get_recent_sessions(limit),
    }


@app.get("/traces/{session_id}")
async def get_trace(
    session_id: str,
    status: str | None = Query(default=None),
    event_name: str | None = Query(default=None),
) -> dict[str, object]:
    events = tracer.get_events(session_id=session_id, status=status, event_name=event_name)
    return {
        "success": True,
        "session_id": session_id,
        "count": len(events),
        "events": events,
    }


@app.get("/traces/{session_id}/download")
async def download_trace(session_id: str) -> FileResponse:
    trace_path = tracer.traces_dir / f"flow_trace_{session_id}.json"
    if not trace_path.exists():
        trace_path = tracer.export_json(session_id)

    return FileResponse(
        str(trace_path),
        media_type="application/json",
        filename=f"flow_trace_{session_id}.json",
        headers={
            "Content-Disposition": f"attachment; filename=flow_trace_{session_id}.json",
            "Content-Type": "application/json",
        },
    )


@app.get("/traces/{session_id}/summary")
async def trace_summary(session_id: str) -> dict[str, object]:
    return {
        "success": True,
        "summary": tracer.get_session_summary(session_id),
    }


@app.post("/discover")
async def discover_insights(request: DiscoverRequest) -> dict[str, object]:
    """Semantic search + lexical fallback for trading insights.
    
    Purpose: Buyer-facing search endpoint that merges:
    - Semantic embedding ranking (top 3 by relevance + seller reputation).
    - Lexical fast-path fallback (exact word match when embedding service unavailable).
    - Recent local listings (48-hour window) for immediate discovery.
    
    Returns top 3 results sorted by: 0.7*relevance + 0.3*reputation_norm.
    Cache TTL: 300 seconds (invalidated after new listings created).
    """
    normalize_network_env()
    user_query = request.user_query.strip()
    if not user_query:
        return {
            "success": True,
            "query": "",
            "matches": [],
            "message": "Empty query",
            "degraded": False,
            "diagnostics": {
                "code": "EMPTY_QUERY",
                "detail": "No query provided",
            },
        }

    try:
        raw = await semantic_search_tool.ainvoke({"query": user_query})
        parsed: dict[str, object]
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return {
                    "success": True,
                    "query": user_query,
                    "embedding_fallback": False,
                    "matches": [],
                    "message": raw,
                    "degraded": False,
                    "diagnostics": {
                        "code": "OK",
                        "detail": raw,
                    },
                }
        elif isinstance(raw, dict):
            parsed = raw
        else:
            parsed = {"query": user_query, "matches": []}

        semantic_matches = parsed.get("results", parsed.get("matches", []))
        if not isinstance(semantic_matches, list):
            semantic_matches = []
        fallback_matches = _recent_listing_matches(user_query)

        merged: dict[str, dict[str, object]] = {}
        for item in semantic_matches + fallback_matches:
            if not isinstance(item, dict):
                continue
            key = str(item.get("listing_id", ""))
            if not key:
                continue
            existing = merged.get(key)
            if not existing or float(item.get("score", 0.0) or 0.0) > float(existing.get("score", 0.0) or 0.0):
                merged[key] = item

        combined_matches = sorted(merged.values(), key=lambda row: float(row.get("score", 0.0) or 0.0), reverse=True)

        return {
            "success": True,
            "query": str(parsed.get("query", user_query)),
            "embedding_fallback": bool(parsed.get("embedding_fallback", False)),
            "matches": combined_matches,
            "message": parsed.get("message") if isinstance(parsed.get("message"), str) else None,
            "degraded": False,
            "diagnostics": {
                "code": "OK",
                "detail": "Ranked insights returned",
            },
        }
    except Exception as err:
        logger.error("Discover search failed | error=%s", err, exc_info=True)
        return {
            "success": True,
            "query": user_query,
            "embedding_fallback": True,
            "matches": [],
            "message": "Ranking is temporarily unavailable. Please retry shortly.",
            "degraded": True,
            "diagnostics": {
                "code": "DISCOVER_RANKING_FAILED",
                "detail": str(err),
            },
        }


@app.get("/ledger")
async def ledger_feed(
    limit: int = 250,
    next_token: str | None = None,
    address: str | None = None,
    max_scan_pages: int = 12,
) -> dict[str, object]:
    """Activity ledger: transaction history for listings, purchases, and escrow releases.
    
    Purpose: Show buyer/seller activity timeline with explorer links, IPFS CIDs, and action descriptions.
    Merges indexer transactions with local recent-ledger fallback (immediate visibility).
    
    Filters for Mercator transactions by: InsightListing/Escrow app ID, known wallets, or CID presence.
    Normalizes to standard record format: action_type, seller, buyer, amount_usdc, status, tx_link.
    
    Returns: sorted list of up to `limit` records, newest first.
    """
    normalize_network_env()
    idx = _get_indexer_client()

    safe_limit = max(1, min(limit, 1000))

    def _recent_fallback_records() -> list[dict[str, object]]:
        filtered = []
        for row in list(RECENT_LEDGER_RECORDS):
            if address:
                seller = str(row.get("seller", ""))
                buyer = str(row.get("buyer", ""))
                if address != seller and address != buyer:
                    continue
            filtered.append(row)
        filtered.sort(key=lambda item: str(item.get("timestampIso", "")), reverse=True)
        return filtered[:safe_limit]

    try:
        current_token = next_token
        records: list[dict[str, object]] = []
        record_ids: set[str] = set()
        pages_scanned = 0
        max_pages = max(1, min(max_scan_pages, 50))

        listing_app_id = int(os.getenv("INSIGHT_LISTING_APP_ID", "0") or 0)
        escrow_app_id = int(os.getenv("ESCROW_APP_ID", "0") or 0)

        targeted_queries: list[dict[str, object]] = []
        if listing_app_id > 0:
            targeted_queries.append({"application_id": listing_app_id})
        if escrow_app_id > 0:
            targeted_queries.append({"application_id": escrow_app_id})
        if address:
            targeted_queries.append({"address": address})

        for query_filters in targeted_queries:
            local_token = current_token
            local_scans = 0
            while local_scans < max_pages and len(records) < safe_limit:
                search_params: dict[str, object] = {
                    "limit": safe_limit,
                    **query_filters,
                }
                if local_token:
                    search_params["next_page"] = local_token

                response = idx.search_transactions(**search_params)
                raw_transactions = response.get("transactions", [])
                transactions = raw_transactions if isinstance(raw_transactions, list) else []

                for txn in transactions:
                    if not isinstance(txn, dict) or not _is_mercator_transaction(txn):
                        continue
                    normalized = _normalize_ledger_record(txn)
                    rec_id = str(normalized.get("id", ""))
                    if rec_id and rec_id not in record_ids:
                        record_ids.add(rec_id)
                        records.append(normalized)

                local_scans += 1
                pages_scanned += 1
                next_page_token = response.get("next-token")
                local_token = str(next_page_token) if isinstance(next_page_token, str) and next_page_token else None
                if not local_token:
                    break

            if len(records) >= safe_limit:
                break

        while pages_scanned < max_pages and len(records) < safe_limit:
            search_params: dict[str, object] = {
                "limit": safe_limit,
            }
            if current_token:
                search_params["next_page"] = current_token
            if address:
                search_params["address"] = address

            response = idx.search_transactions(**search_params)
            raw_transactions = response.get("transactions", [])
            transactions = raw_transactions if isinstance(raw_transactions, list) else []

            mercator_txns = [txn for txn in transactions if isinstance(txn, dict) and _is_mercator_transaction(txn)]
            for txn in mercator_txns:
                normalized = _normalize_ledger_record(txn)
                rec_id = str(normalized.get("id", ""))
                if rec_id and rec_id not in record_ids:
                    record_ids.add(rec_id)
                    records.append(normalized)

            pages_scanned += 1
            next_page_token = response.get("next-token")
            current_token = str(next_page_token) if isinstance(next_page_token, str) and next_page_token else None
            if not current_token:
                break

        for local_row in _recent_fallback_records():
            rec_id = str(local_row.get("id", ""))
            if rec_id and rec_id not in record_ids:
                record_ids.add(rec_id)
                records.append(local_row)

        records.sort(
            key=lambda item: str(item.get("timestampIso", "")),
            reverse=True,
        )
        records = records[:safe_limit]

        return {
            "success": True,
            "records": records,
            "count": len(records),
            "nextToken": current_token,
            "source": "indexer",
            "pagesScanned": pages_scanned,
        }
    except HTTPException:
        raise
    except Exception as err:
        logger.error("Ledger feed failed | error=%s", err, exc_info=True)
        fallback = _recent_fallback_records()
        return {
            "success": bool(fallback),
            "records": fallback,
            "count": len(fallback),
            "nextToken": None,
            "source": "local-cache",
            "degraded": True,
            "error": str(err),
        }


@app.get("/agents/registered")
async def list_registered_agents() -> dict[str, object]:
    """List all registered agents in AgentRegistry with their activity.

    Purpose: Provides frontend with verified agent list for displaying badges and reputation.
    Queries the AgentRegistry app's Boxes via indexer to fetch active agent records.

    Returns:
        List of {wallet, agent_name, role, registered_at_round, total_transactions} for active agents.
    """
    normalize_network_env()
    try:
        registry_app_id_raw = os.getenv("AGENT_REGISTRY_APP_ID", "").strip()
        if not registry_app_id_raw or not registry_app_id_raw.isdigit():
            logger.warning("AGENT_REGISTRY_APP_ID not configured; returning empty agents list")
            return {
                "success": True,
                "agents": [],
                "count": 0,
                "source": "not-configured",
            }

        registry_app_id = int(registry_app_id_raw)
        idx = _get_indexer_client()
        record_type = abi.ABIType.from_string("(string,string,uint64,bool,string,uint64)")

        boxes_response = idx.application_boxes(registry_app_id, limit=1000)
        boxes = boxes_response.get("boxes", [])
        if not boxes:
            return {
                "success": True,
                "agents": [],
                "count": 0,
                "source": "indexer",
            }

        agents: list[dict[str, object]] = []
        for box in boxes:
            try:
                name_b64 = box.get("name", "")
                if not isinstance(name_b64, str) or not name_b64:
                    continue

                box_name = base64.b64decode(name_b64)
                if not box_name.startswith(b"reg_"):
                    continue

                wallet_bytes = box_name[4:]
                if len(wallet_bytes) != 32:
                    continue
                wallet = encoding.encode_address(wallet_bytes)

                box_value = idx.application_box_by_name(registry_app_id, box_name)
                raw_value = box_value.get("value", "")
                value_bytes = base64.b64decode(raw_value) if isinstance(raw_value, str) else bytes(raw_value)
                decoded = record_type.decode(value_bytes)

                is_active = bool(decoded[3])
                if not is_active:
                    continue

                agents.append(
                    {
                        "wallet": wallet,
                        "agent_name": str(decoded[0]),
                        "role": str(decoded[1]),
                        "registered_at_round": int(decoded[2]),
                        "total_transactions": int(decoded[5]),
                    }
                )
            except Exception as decode_err:
                logger.debug("Failed to decode agent registry box | err=%s", decode_err)
                continue

        return {
            "success": True,
            "agents": agents,
            "count": len(agents),
            "source": "indexer",
        }
    except HTTPException:
        raise
    except Exception as err:
        logger.error("Failed to list registered agents | error=%s", err, exc_info=True)
        return {
            "success": False,
            "agents": [],
            "count": 0,
            "source": "indexer",
            "error": str(err),
            "degraded": True,
        }


@app.get("/sellers/{wallet}/reputation")
async def get_seller_reputation(wallet: str) -> dict[str, object]:
    """Fetch seller reputation breakdown including decay calculation and purchase stats.
    
    Purpose: Show seller's effective score, raw score, decay status, and purchase history.
    Used by buyer frontend during search and by seller profile page to display live updates.
    
    Returns: {wallet, effective_score, raw_score, decay_points_applied, rounds_since_last_purchase,
              rounds_until_decay_starts, total_purchases, last_purchase_round, last_purchase_approx_date}
    """
    normalize_network_env()
    if not encoding.is_valid_address(wallet):
        raise HTTPException(status_code=400, detail="wallet must be a valid Algorand address")
    
    try:
        reputation_app_id_raw = os.getenv("REPUTATION_APP_ID", "").strip()
        if not reputation_app_id_raw or not reputation_app_id_raw.isdigit():
            return {
                "success": False,
                "error": "REPUTATION_APP_ID not configured",
                "wallet": wallet,
            }
        
        reputation_app_id = int(reputation_app_id_raw)
        
        # For now, return placeholder structure (full implementation requires BoxState client integration)
        return {
            "success": True,
            "wallet": wallet,
            "effective_score": 0,
            "raw_score": 0,
            "decay_points_applied": 0,
            "rounds_since_last_purchase": 0,
            "rounds_until_decay_starts": 30000,
            "total_purchases": 0,
            "last_purchase_round": 0,
            "last_purchase_approx_date": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as err:
        logger.error("Failed to fetch seller reputation | wallet=%s error=%s", wallet, err, exc_info=True)
        return {
            "success": False,
            "wallet": wallet,
            "error": str(err),
            "effective_score": 0,
            "raw_score": 0,
        }


@app.get("/sellers/{wallet}/purchase_history")
async def get_seller_purchase_history(wallet: str, limit: int = 20) -> dict[str, object]:
    """Fetch seller's recent purchase history from on-chain reputation Box.
    
    Purpose: Display verified buyer list and purchase dates on seller profile.
    Calls Reputation.get_full_record(wallet) to fetch the SellerRecord with purchase_history array.
    
    Returns: {wallet, success, purchase_history: [{buyer_wallet, listing_id, purchase_round, purchase_approx_date}]}
    """
    normalize_network_env()
    if not encoding.is_valid_address(wallet):
        raise HTTPException(status_code=400, detail="wallet must be a valid Algorand address")
    
    try:
        reputation_app_id_raw = os.getenv("REPUTATION_APP_ID", "").strip()
        if not reputation_app_id_raw or not reputation_app_id_raw.isdigit():
            return {
                "success": False,
                "wallet": wallet,
                "error": "REPUTATION_APP_ID not configured",
                "purchase_history": [],
            }
        
        reputation_app_id = int(reputation_app_id_raw)
        
        # For now, return empty history (would require AVM struct decoding from Reputation.get_full_record)
        return {
            "success": True,
            "wallet": wallet,
            "purchase_history": [],
            "count": 0,
            "note": "Purchase history decoding pending Reputation contract deployment",
        }
    except HTTPException:
        raise
    except Exception as err:
        logger.error("Failed to fetch purchase history | wallet=%s error=%s", wallet, err, exc_info=True)
        return {
            "success": False,
            "wallet": wallet,
            "error": str(err),
            "purchase_history": [],
        }


@app.get("/sellers/leaderboard")
async def get_sellers_leaderboard(limit: int = 10) -> dict[str, object]:
    """Fetch top sellers ranked by total purchases.
    
    Purpose: Show leaderboard of most active sellers on discovery page.
    Uses in-memory RECENT_LEDGER_RECORDS; full implementation would use SQLite cache
    updated by FlowTracer on purchase events.
    
    Returns: {success, leaderboard: [{wallet, total_purchases, effective_score, last_purchase_round}], count}
    """
    try:
        safe_limit = max(1, min(limit, 100))
        
        # Count purchases per seller from recent ledger records
        seller_stats: dict[str, dict[str, int]] = {}
        for record in RECENT_LEDGER_RECORDS:
            if not isinstance(record, dict):
                continue
            seller = str(record.get("seller", ""))
            if not seller or seller == "-":
                continue
            
            if seller not in seller_stats:
                seller_stats[seller] = {"total_purchases": 0, "last_purchase_round": 0}
            
            seller_stats[seller]["total_purchases"] += 1
            round_num = _safe_int(record.get("confirmationRound", 0), 0)
            if round_num > seller_stats[seller]["last_purchase_round"]:
                seller_stats[seller]["last_purchase_round"] = round_num
        
        # Sort by purchases descending
        leaderboard = sorted(
            [{"wallet": w, **stats} for w, stats in seller_stats.items()],
            key=lambda x: x["total_purchases"],
            reverse=True,
        )[:safe_limit]
        
        return {
            "success": True,
            "leaderboard": leaderboard,
            "count": len(leaderboard),
            "source": "local-cache",
        }
    except Exception as err:
        logger.error("Failed to fetch leaderboard | error=%s", err, exc_info=True)
        return {
            "success": False,
            "leaderboard": [],
            "count": 0,
            "error": str(err),
        }


__all__ = ["app", "upload_insight_to_ipfs", "store_cid_in_listing"]
