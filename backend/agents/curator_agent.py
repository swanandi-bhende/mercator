"""Curator agent: gather market snapshots, synthesise insights, publish listings.

This module provides a small orchestration layer used by the scheduler
and the admin/status endpoints. It is intentionally simple so tests can
monkeypatch internals easily.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
import base64
import os as _os
import logging as _logging

from backend.utils.identity import generate_manifest, verify_manifest_locally, private_key_from_mnemonic

from backend.agents.insight_synthesiser import SynthesisedInsight, synthesise_insight
from backend.agents.market_data_fetcher import MarketSnapshot, fetch_market_snapshot
from backend.utils.db import (
    fetch_curator_recent_runs,
    fetch_curator_today_stats,
    initialise_curator_schema,
    record_curator_error,
    record_curator_run,
)
from backend.tools.semantic_search import get_insight_listing_client, invalidate_listing_cache
from backend.utils.runtime_env import normalize_network_env
from backend.utils.flow_tracer import tracer
from backend.utils.error_handler import ErrorHandler, ErrorCode
import sqlite3
import os
from backend.utils.runtime_env import load_repo_env_files, normalize_network_env
from backend.utils.ws_manager import ws_manager
from backend.utils.flow_tracer import tracer
from backend.utils.error_handler import retry_with_backoff

logger = logging.getLogger(__name__)

load_repo_env_files()
normalize_network_env()

DEFAULT_SYMBOLS = ("RELIANCE.NS", "TCS.NS", "INFY.NS")
DEFAULT_MIN_DATA_QUALITY_SCORE = 60
DEFAULT_CYCLE_PAUSE_SECONDS = 5
DEFAULT_LISTING_URL = "http://127.0.0.1:8000/list"


@dataclass(slots=True)
class CuratorRunResult:
    run_id: str
    symbol: str
    snapshot_quality: int = 0
    synthesis_quality: str = ""
    published: bool = False
    skip_reason: str = ""
    listing_tx_id: str = ""
    insight_text: str = ""
    price_usdc: float = 0.0
    started_at: str = ""
    completed_at: str = ""
    error: str = ""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)).strip())
    except Exception:
        return default


def _quality_threshold_from_env(name: str, default: float) -> int:
    raw = _float_env(name, default)
    return int(round(raw * 100)) if 0.0 <= raw <= 1.0 else int(round(raw))


def _symbols_from_env() -> list[str]:
    raw = os.getenv("CURATOR_DEFAULT_SYMBOLS", ",".join(DEFAULT_SYMBOLS))
    symbols = [item.strip() for item in raw.split(",") if item.strip()]
    return symbols or list(DEFAULT_SYMBOLS)


def _listing_url() -> str:
    configured = os.getenv("CURATOR_LISTING_URL", os.getenv("LISTING_API_URL", DEFAULT_LISTING_URL)).strip()
    if configured.endswith("/list"):
        return configured
    return configured.rstrip("/") + "/list"


def _quality_label(quality_score: float, confidence: float) -> str:
    return "high" if quality_score >= 70 and confidence >= 70 else ("medium" if confidence >= 50 else "low")


def _percent_int(value: Any) -> int:
    try:
        raw = float(value)
    except Exception:
        return 0
    if 0.0 <= raw <= 1.0:
        raw *= 100.0
    return max(0, min(100, int(round(raw))))


def _insight_confidence(insight: SynthesisedInsight | Any) -> int:
    if hasattr(insight, "confidence_score"):
        return _percent_int(getattr(insight, "confidence_score"))
    if hasattr(insight, "confidence"):
        return _percent_int(getattr(insight, "confidence"))
    return 0


def _snapshot_field(snapshot: MarketSnapshot, *names: str) -> Any:
    for name in names:
        if hasattr(snapshot, name):
            value = getattr(snapshot, name)
            if value is not None:
                return value
    return None


def _price_change_pct(snapshot: MarketSnapshot) -> float | None:
    current_price = _snapshot_field(snapshot, "last_price", "current_price")
    previous_close = _snapshot_field(snapshot, "previous_close")
    if current_price is None or previous_close in {None, 0}:
        return None
    return round(((float(current_price) - float(previous_close)) / float(previous_close)) * 100.0, 4)


def _volume_ratio(snapshot: MarketSnapshot) -> float | None:
    volume_today = _snapshot_field(snapshot, "volume_today", "volume")
    average_volume = _snapshot_field(snapshot, "avg_volume_5d", "average_volume")
    if volume_today is None or not average_volume:
        return None
    try:
        if float(average_volume) <= 0:
            return None
        return round(float(volume_today) / float(average_volume), 4)
    except Exception:
        return None


def _insight_text(insight: SynthesisedInsight) -> str:
    text = getattr(insight, "insight_text", "") or getattr(insight, "headline", "")
    return str(text).strip()


def _error_type_for_message(message: str, stage: str = "curator") -> str:
    lowered = message.lower()
    if "429" in lowered or "rate limit" in lowered:
        return "newsapi_rate_limit"
    if "parse" in lowered or "json" in lowered:
        return "gemini_parse_failure"
    if "timeout" in lowered or "timed out" in lowered:
        return "yfinance_timeout" if stage == "snapshot" else "listing_endpoint_error"
    if stage == "listing":
        return "listing_endpoint_error"
    if stage == "snapshot":
        return "yfinance_timeout"
    return "curator_error"


def _persist_result(result: CuratorRunResult, snapshot: MarketSnapshot | None = None, insight: SynthesisedInsight | None = None, listing_ipfs_cid: str = "") -> None:
    initialise_curator_schema()
    quality_score = _percent_int(getattr(snapshot, "data_quality_score", 0)) if snapshot is not None else 0
    confidence = _insight_confidence(insight) if insight is not None else 0
    record_curator_run(
        {
            "run_id": result.run_id,
            "run_started_at": result.started_at,
            "run_completed_at": result.completed_at,
            "symbol": result.symbol,
            "snapshot_quality_score": quality_score,
            "volume_ratio": _volume_ratio(snapshot) if snapshot is not None else None,
            "price_change_pct": _price_change_pct(snapshot) if snapshot is not None else None,
            "headlines_found": len(getattr(insight, "key_metrics_cited", getattr(insight, "evidence", []))) if insight is not None else 0,
            "synthesis_quality": result.synthesis_quality,
            "confidence_score": confidence,
            "directional_view": getattr(insight, "directional_view", getattr(insight, "direction", "")) if insight is not None else "",
            "insight_text": result.insight_text,
            "price_usdc": result.price_usdc,
            "published": 1 if result.published else 0,
            "skip_reason": result.skip_reason,
            "listing_tx_id": result.listing_tx_id,
            "listing_ipfs_cid": listing_ipfs_cid,
            "error": result.error,
        }
    )
    if result.error:
        record_curator_error(
            {
                "error_id": uuid4().hex,
                "run_id": result.run_id,
                "error_type": _error_type_for_message(result.error, stage="listing" if "listing" in result.error.lower() else "curator"),
                "error_detail": result.error,
                "occurred_at": _utc_now_iso(),
            }
        )


async def _publish_listing(insight_text: str, price_usdc: float) -> tuple[str, str]:
    payload = {
        "insight_text": insight_text,
        "price": float(price_usdc),
        "seller_wallet": os.getenv("CURATOR_WALLET_ADDRESS", "").strip(),
        "source_type": "curator_agent",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(_listing_url(), json=payload)

    if response.status_code != 200:
        raise RuntimeError(response.text or f"listing endpoint returned HTTP {response.status_code}")

    try:
        body = response.json()
    except Exception:
        body = {}

    tx_id = str(body.get("transaction_id") or body.get("txId") or body.get("tx_id") or "").strip()
    listing_ipfs_cid = str(body.get("cid") or body.get("ipfs_cid") or "").strip()
    if not tx_id:
        raise RuntimeError(response.text or "listing response missing transaction_id")
    return tx_id, listing_ipfs_cid


async def run_cycle_for_symbol(symbol: str) -> CuratorRunResult:
    run_id = str(uuid4())
    started_at = _utc_now_iso()
    min_quality = _quality_threshold_from_env("CURATOR_MIN_DATA_QUALITY_SCORE", DEFAULT_MIN_DATA_QUALITY_SCORE)
    result = CuratorRunResult(run_id=run_id, symbol=symbol.strip().upper(), started_at=started_at)
    snapshot: MarketSnapshot | None = None
    insight: SynthesisedInsight | None = None
    listing_ipfs_cid = ""

    try:
        try:
            snapshot = await asyncio.to_thread(fetch_market_snapshot, symbol)
        except Exception as exc:
            # Map market data provider issues to MARKET_DATA_UNAVAILABLE
            raise ErrorHandler.handle(exc, {"function": "run_cycle_for_symbol", "symbol": symbol}) from exc
        snapshot_quality = _percent_int(getattr(snapshot, "data_quality_score", 0))
        result.snapshot_quality = snapshot_quality
        if snapshot_quality < min_quality:
            result.skip_reason = f"data_quality_score {snapshot_quality} below threshold {min_quality}"
            return result

        try:
            insight = await asyncio.to_thread(synthesise_insight, snapshot)
        except Exception as exc:
            # Map model/Gemini errors to agent errors via ErrorHandler
            raise ErrorHandler.handle(exc, {"function": "run_cycle_for_symbol", "symbol": symbol}) from exc
        insight_text = _insight_text(insight)
        result.insight_text = insight_text
        result.price_usdc = float(insight.price_usdc)
        confidence_score = _insight_confidence(insight)
        result.synthesis_quality = getattr(insight, "synthesis_quality", _quality_label(snapshot_quality, confidence_score))

        if result.synthesis_quality == "low":
            result.skip_reason = f"synthesis confidence {confidence_score} below threshold 50"
            return result

        tx_id, listing_ipfs_cid = await _publish_listing(insight_text, insight.price_usdc)
        result.published = True
        result.listing_tx_id = tx_id
        result.skip_reason = ""
        return result
    except Exception as exc:  # pragma: no cover - exercised by tests
        result.error = str(exc)
        result.published = False
        logger.exception("Curator cycle failed for symbol=%s", symbol)
        return result
    finally:
        result.completed_at = _utc_now_iso()
        try:
            _persist_result(result, snapshot=snapshot, insight=insight, listing_ipfs_cid=listing_ipfs_cid)
        except Exception:
            logger.exception("Failed to persist curator run %s", result.run_id)


@retry_with_backoff()
async def run_full_cycle() -> list[CuratorRunResult]:
    tracer.start_session("curator_cycle")
    tracer.record(
        "curator.cycle_started",
        "success",
        plain_english_description="Curator cycle started",
    )
    results: list[CuratorRunResult] = []
    symbols = _symbols_from_env()
    for index, symbol in enumerate(symbols):
        result = await run_cycle_for_symbol(symbol)
        results.append(result)
        if index < len(symbols) - 1:
            await asyncio.sleep(DEFAULT_CYCLE_PAUSE_SECONDS)

    published_count = len([item for item in results if item.published])
    skipped_count = len([item for item in results if not item.published])
    next_run_at = ""
    try:
        from backend.main import scheduler  # Local import avoids module import cycles.

        job = scheduler.get_job("curator_cycle")
        if job is not None and getattr(job, "next_run_time", None) is not None:
            next_run_at = job.next_run_time.isoformat()
    except Exception:
        next_run_at = ""

    await ws_manager.broadcast(
        "curator_cycle_complete",
        {
            "symbols_processed": len(symbols),
            "insights_published": published_count,
            "insights_skipped": skipped_count,
            "next_run_at": next_run_at,
        },
    )
    tracer.export_json()
    return results


async def expire_stale_listings() -> None:
    """Background job: find listings created long ago with no sold/expired event and call check_and_expire.

    This queries the local flow_events DB for 'listing.asa_creation_completed' events older than
    EXPIRY_HOURS (env) and without a corresponding 'listing.sold' or 'listing.expired' event.
    For each stale listing found, call the on-chain `check_and_expire(listing_id)` method as a
    separate transaction. Limit to 20 expirations per run.
    """
    normalize_network_env()
    expiry_hours = int(os.getenv("EXPIRY_HOURS", "48"))
    max_per_run = int(os.getenv("EXPIRY_EXPIRATIONS_PER_RUN", "20"))

    db_path = tracer.db_path
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        sql = f"""
            SELECT DISTINCT json_extract(metadata, '$.listing_id') AS listing_id
            FROM flow_events
            WHERE event_name = 'listing.asa_creation_completed'
            AND timestamp_iso < datetime('now', '-{expiry_hours} hours')
            AND json_extract(metadata, '$.listing_id') NOT IN (
                SELECT json_extract(metadata, '$.listing_id') FROM flow_events WHERE event_name IN ('listing.sold', 'listing.expired')
            )
            LIMIT ?
        """
        rows = conn.execute(sql, (max_per_run,)).fetchall()
        listing_ids = [int(row['listing_id']) for row in rows if row['listing_id'] is not None]
    except Exception as exc:
        logger.exception("Failed to query flow_events for stale listings: %s", exc)
        listing_ids = []
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if not listing_ids:
        return

    client = None
    try:
        client = get_insight_listing_client()
    except Exception:
        logger.exception("InsightListing client unavailable for expiry job")

    expirations = 0
    for lid in listing_ids:
        if expirations >= max_per_run:
            break
        try:
            if client is None:
                logger.warning("Skipping expiry for %s: no client", lid)
                continue
            # Call check_and_expire as a separate transaction
            try:
                await asyncio.to_thread(client.send.check_and_expire, lid)
            except Exception:
                # Some clients expose synchronous send methods; try calling directly
                try:
                    client.send.check_and_expire(lid)
                except Exception as exc:
                    logger.exception("Failed to submit check_and_expire for %s: %s", lid, exc)
                    continue

            tracer.record(
                "listing.expired",
                "success",
                plain_english_description=f"Expired listing {lid} marked expired by maintenance job",
                metadata={"listing_id": lid},
            )
            expirations += 1
        except Exception as exc:
            logger.exception("Error expiring listing %s: %s", lid, exc)

    if expirations > 0:
        try:
            invalidate_listing_cache()
        except Exception:
            logger.exception("Failed to invalidate listing cache after expirations")


def curator_status_snapshot(scheduler: Any | None = None) -> dict[str, Any]:
    job = None
    scheduler_running = False
    if scheduler is not None:
        try:
            job = scheduler.get_job("curator_cycle")
            scheduler_running = bool(getattr(scheduler, "running", False))
        except Exception:
            job = None
            scheduler_running = False

    next_fire_time = "not_scheduled"
    if job is not None and getattr(job, "next_run_time", None) is not None:
        next_fire_time = job.next_run_time.isoformat()

    recent_runs = fetch_curator_recent_runs(5)
    today_stats = fetch_curator_today_stats()
    symbol_count = len(_symbols_from_env())
    return {
        "scheduler_running": scheduler_running,
        "next_fire_time": next_fire_time,
        "last_5_runs": recent_runs,
        "today_stats": today_stats,
        "newsapi_calls_today": today_stats.get("total_runs", 0) * symbol_count,
    }


async def ensure_registered(
    *,
    agent_name: str = "Mercator Curator Agent",
    role: str = "curator",
    wallet_env: str = "CURATOR_WALLET_ADDRESS",
    mnemonic_env: str = "CURATOR_MNEMONIC",
) -> None:
    """Best-effort identity registration preflight for an agent role.

    This currently signs/verifies the role manifest locally and logs what
    would be submitted on-chain when AgentRegistry app ID is configured.
    """
    logger = _logging.getLogger(__name__)
    wallet = _os.getenv(wallet_env, "").strip()
    mnemonic = _os.getenv(mnemonic_env, "").strip()
    if not wallet or not mnemonic:
        logger.info("%s or %s not set; skipping %s registration check", wallet_env, mnemonic_env, role)
        return

    private_key = private_key_from_mnemonic(mnemonic)
    manifest_json, signature_b64 = generate_manifest(agent_name, wallet, role, private_key)

    if not verify_manifest_locally(manifest_json, signature_b64, wallet):
        logger.error("Local manifest verification failed for %s wallet %s; aborting registration attempt", role, wallet)
        return

    try:
        from algokit_utils import AlgorandClient

        _ = AlgorandClient.from_environment()
        app_id_raw = _os.getenv("AGENT_REGISTRY_APP_ID", "").strip()
        if not app_id_raw or not app_id_raw.isdigit():
            logger.info("AGENT_REGISTRY_APP_ID not configured; skipping remote %s registration check", role)
            return

        app_id = int(app_id_raw)
        logger.info(
            "AgentRegistry app id %d configured; %s (%s) verified locally and ready for register() call.",
            app_id,
            role,
            wallet,
        )
        logger.debug("Prepared %s signature: %s", role, signature_b64)
    except Exception:
        logger.info("algokit_utils unavailable; skipping on-chain %s registration step", role)
