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
import json
import logging
import os
import hashlib
import time
import warnings
from uuid import uuid4
from typing import Any
import requests
from datetime import datetime, timezone
from collections import deque
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from algosdk import mnemonic, transaction
from algosdk import encoding
from algosdk import account
from algosdk.error import AlgodHTTPError
from algosdk.logic import get_application_address
from algosdk.v2client import algod, indexer

warnings.filterwarnings(
    "ignore",
    message="Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.",
    category=UserWarning,
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
)
from backend.utils.runtime_env import configure_demo_logging, normalize_network_env, warn_missing_required_env
from backend.utils.error_handler import contract_error, ipfs_down

try:
    from contracts.insight_listing import InsightListingClient  # noqa: F401
except Exception:  # pragma: no cover
    InsightListingClient = None  # type: ignore[assignment]

try:
    from utils.ipfs import (
        IPFSUploadError,
        ListingStoreError,
        upload_insight_to_ipfs,
        store_cid_in_listing,
        fetch_insight_from_ipfs,
        PINATA_BASE_URL,
    )
except ModuleNotFoundError:
    from backend.utils.ipfs import (
        IPFSUploadError,
        ListingStoreError,
        upload_insight_to_ipfs,
        store_cid_in_listing,
        fetch_insight_from_ipfs,
        PINATA_BASE_URL,
    )


normalize_network_env()
demo_logger = configure_demo_logging()

app = FastAPI(title="Mercator Backend")
logger = logging.getLogger("mercator.backend")

EXPLORER_TX_BASE = os.getenv("EXPLORER_TX_BASE", "https://lora.algokit.io/testnet/tx").rstrip("/")

frontend_origins_raw = os.getenv("FRONTEND_ORIGIN", "").strip()
frontend_origins = [origin.strip() for origin in frontend_origins_raw.split(",") if origin.strip()]

allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
for origin in frontend_origins:
    if origin not in allowed_origins:
        allowed_origins.append(origin)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("mercator.log", mode="a"),
    ],
    force=True,
)


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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ListingRequest(BaseModel):
    insight_text: str
    price: float
    seller_wallet: str


class DemoPurchaseRequest(BaseModel):
    user_query: str
    buyer_address: str | None = None
    user_approval_input: str = "approve"
    force_buy_for_test: bool = True
    target_listing_id: int | None = None


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


def _ensure_listing_app_funded(app_id: int, preferred_sender: str = "") -> None:
    """Top up InsightListing app contract account to cover state box storage.

    Target: min_balance + 300K micro-Algo (box storage buffer).
    Purpose: Prevent app account errors when buyers/sellers create/redeem listings.
    """
    client = _get_algod_client()
    app_address = get_application_address(app_id)
    app_info = client.account_info(app_address)

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
            info = client.account_info(cand_sender)
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
        raise HTTPException(
            status_code=400,
            detail=(
                "Insufficient Algo balance to fund listing app account. "
                "Top up DEPLOYER/SELLER/BUYER wallet and retry."
            ),
        )

    params = client.suggested_params()
    pay_txn = transaction.PaymentTxn(
        sender=sender,
        sp=params,
        receiver=app_address,
        amt=top_up,
    )
    tx_id = client.send_transaction(pay_txn.sign(private_key))
    transaction.wait_for_confirmation(client, tx_id, 4)


def _is_transient_chain_error(err: Exception) -> bool:
    """Return True for intermittent network/SSL/timeout chain errors worth retrying."""
    message = str(err).lower()
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


@app.on_event("startup")
def startup_checks() -> None:
    """Startup hook to normalize env and warn on missing required keys.

    Micropayment role: preflight guardrail before serving listing/payment endpoints.
    """
    normalize_network_env()
    warn_missing_required_env(logger)


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
    normalize_network_env()
    timestamp = datetime.now(timezone.utc).isoformat()

    services: dict[str, dict[str, str]] = {
        "api": {"status": "ok", "detail": "FastAPI service is running"},
        "algod": {"status": "unknown", "detail": "Not checked"},
        "indexer": {"status": "unknown", "detail": "Not checked"},
        "listing_app": {"status": "unknown", "detail": "Not checked"},
        "escrow_app": {"status": "unknown", "detail": "Not checked"},
    }

    overall_status = "ok"

    try:
        algod_client = _get_algod_client()
        params = algod_client.suggested_params()
        if params is None:
            raise RuntimeError("No suggested params returned")
        services["algod"] = {"status": "ok", "detail": "Connected"}
    except Exception as err:
        overall_status = "degraded"
        services["algod"] = {"status": "error", "detail": str(err)}

    try:
        idx = _get_indexer_client()
        idx.search_transactions(limit=1)
        services["indexer"] = {"status": "ok", "detail": "Connected"}
    except Exception as err:
        overall_status = "degraded"
        services["indexer"] = {"status": "error", "detail": str(err)}

    listing_app = os.getenv("INSIGHT_LISTING_APP_ID", "").strip()
    if listing_app and listing_app.isdigit() and int(listing_app) > 0:
        services["listing_app"] = {"status": "ok", "detail": f"Configured ({listing_app})"}
    else:
        overall_status = "degraded"
        services["listing_app"] = {"status": "error", "detail": "INSIGHT_LISTING_APP_ID missing/invalid"}

    escrow_app = os.getenv("ESCROW_APP_ID", "").strip()
    if escrow_app and escrow_app.isdigit() and int(escrow_app) > 0:
        services["escrow_app"] = {"status": "ok", "detail": f"Configured ({escrow_app})"}
    else:
        overall_status = "degraded"
        services["escrow_app"] = {"status": "error", "detail": "ESCROW_APP_ID missing/invalid"}

    return {
        "status": overall_status,
        "timestamp": timestamp,
        "services": services,
    }


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


def _probe_gateway(url: str, *, timeout: int = 8, headers: dict[str, str] | None = None) -> dict[str, object]:
    """Execute HTTP probe against gateway/service and return status summary.

    Micropayment role: monitors IPFS/pinata connectivity for listing and delivery reliability.
    """
    started = time.perf_counter()
    try:
        response = requests.get(url, timeout=timeout, headers=headers or {})
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


def _collect_ipfs_health(now: datetime) -> dict[str, object]:
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
    pinata_probe = _probe_gateway(f"{PINATA_BASE_URL}/data/testAuthentication", headers=pinata_headers)

    gateway_checks = [_probe_gateway(url) for url in gateways[:6]]

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


def _collect_algorand_status(now: datetime) -> dict[str, object]:
    """Collect Algorand node sync, latency, and fee telemetry.

    Micropayment role: confirms chain readiness for x402 payments and contract calls.
    """
    started = time.perf_counter()
    try:
        client = _get_algod_client()
        status = client.status()
        params = client.suggested_params()
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


def _collect_environment_panel() -> dict[str, object]:
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
                account_info = algod_client.account_info(address)
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
    environment = _collect_environment_panel()
    events = _collect_system_events(now)
    ipfs_health = _collect_ipfs_health(now)
    algorand_status = _collect_algorand_status(now)
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
        "ipfs": _collect_ipfs_health(now),
    }


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
        "algorand": _collect_algorand_status(now),
    }


@app.post("/ops/algorand/test")
async def ops_algorand_test(request: Request) -> dict[str, object]:
    """Run active Algorand telemetry test.

    Micropayment role: operator-triggered validation for chain-side reliability.
    """
    _require_operator(request)
    now = datetime.now(timezone.utc)
    status = _collect_algorand_status(now)
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
async def create_listing(request: ListingRequest) -> dict[str, int | str]:
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
        return _error_response(500, "INSIGHT_LISTING_APP_ID is not configured")

    try:
        listing_app_id = int(listing_app_id_raw)
    except ValueError as err:
        logger.error("Invalid listing app id in environment | value=%s", listing_app_id_raw)
        return _error_response(500, "INSIGHT_LISTING_APP_ID is invalid")

    try:
        signing_mnemonic, signer_address, signer_exact_match = _resolve_signer_for_wallet(request.seller_wallet)
    except HTTPException as err:
        return _error_response(err.status_code, str(err.detail))

    logger.info(
        "Validation passed for seller %s (effective signer=%s exact_match=%s)",
        request.seller_wallet,
        signer_address,
        signer_exact_match,
    )

    try:
        effective_seller_wallet = signer_address

        if request.seller_wallet != effective_seller_wallet:
            logger.warning(
                "Using effective seller wallet %s instead of requested wallet %s",
                effective_seller_wallet,
                request.seller_wallet,
            )

        logger.info("IPFS upload started | seller=%s", effective_seller_wallet)
        cid = await upload_insight_to_ipfs(request.insight_text)
        logger.info("IPFS upload complete, cid=%s", cid)

        micro_price = int(request.price * 1_000_000)
        listing_id = 0
        asa_id = 0
        tx_id = ""
        attempts = 3
        last_chain_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                _ensure_listing_app_funded(listing_app_id, preferred_sender=signer_address)

                logger.info(
                    "ASA creation attempted | seller=%s price_micro=%s app_id=%s attempt=%s/%s",
                    effective_seller_wallet,
                    micro_price,
                    listing_app_id,
                    attempt,
                    attempts,
                )
                listing_id, asa_id = store_cid_in_listing(
                    cid=cid,
                    listing_app_id=listing_app_id,
                    seller_address=effective_seller_wallet,
                    price=micro_price,
                    signer_mnemonic=signing_mnemonic,
                )

                logger.info(
                    "On-chain listing submitted: listing_id=%s asa_id=%s",
                    listing_id,
                    asa_id,
                )
                demo_logger.info("Seller upload complete")
                demo_logger.info("On-chain ASA created")

                tx_id = await _poll_for_listing_confirmation(
                    app_id=listing_app_id,
                    sender=effective_seller_wallet,
                    cid=cid,
                )
                logger.info("Transaction confirmed: tx_id=%s", tx_id)
                break
            except Exception as chain_err:
                last_chain_error = chain_err
                if attempt == attempts or not _is_transient_chain_error(chain_err):
                    raise
                logger.warning(
                    "Transient chain error during /list; retrying | attempt=%s/%s error=%s",
                    attempt,
                    attempts,
                    chain_err,
                )
                await asyncio.sleep(min(3, attempt))

        if not tx_id and last_chain_error is not None:
            raise last_chain_error

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
            }
        )
        try:
            clear_semantic_search_cache()
        except Exception:
            # Never block listing success on cache invalidation.
            pass
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

    return {
        "success": True,
        "transaction_id": tx_id,
        "txId": tx_id,
        "explorer_url": f"{EXPLORER_TX_BASE}/{tx_id}/",
        "message": "Insight listed on-chain and pinned on IPFS",
        "cid": cid,
        "listing_id": listing_id,
        "asa_id": asa_id,
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
    buyer_address = (request.buyer_address or os.getenv("BUYER_WALLET", "").strip() or os.getenv("BUYER_ADDRESS", "").strip() or os.getenv("DEPLOYER_ADDRESS", "").strip())
    result = await run_agent(
        user_query=request.user_query,
        buyer_address=buyer_address,
        user_approval_input=request.user_approval_input,
        force_buy_for_test=request.force_buy_for_test,
        target_listing_id=request.target_listing_id,
    )

    final_insight_text = _extract_final_insight_text(result if isinstance(result, dict) else {})
    return {
        "success": bool(result.get("success", False)) if isinstance(result, dict) else False,
        "final_insight_text": final_insight_text,
        "result": result,
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
            parsed = json.loads(raw)
        elif isinstance(raw, dict):
            parsed = raw
        else:
            parsed = {"query": user_query, "matches": []}

        semantic_matches = parsed.get("matches", []) if isinstance(parsed.get("matches", []), list) else []
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


__all__ = ["app", "upload_insight_to_ipfs", "store_cid_in_listing"]
