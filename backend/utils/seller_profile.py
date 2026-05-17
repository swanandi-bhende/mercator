from __future__ import annotations

import asyncio
import base64
import math
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import quote

from cachetools import TTLCache

try:
    from algosdk import encoding as algo_encoding
except Exception:  # pragma: no cover - the module is still testable without algosdk at import time
    algo_encoding = None

from .db import get_db_path, initialise_seller_profile_schema


@dataclass
class DecayInfo:
    last_updated_at: Optional[str]
    decay_rate: Optional[float]
    decay_points_applied: Optional[int]


@dataclass
class SellerStats:
    seller_wallet: str
    total_purchases: int
    total_usdc_earned_micro: float
    avg_price_usdc: Optional[float]
    first_listing_date: Optional[str]
    last_purchase_date: Optional[str]
    recent_evaluations_avg_score: Optional[float]
    display_name: str
    registered_agent_name: Optional[str]
    registered_agent_role: Optional[str]
    registered_at_round: Optional[int]
    trust_summary: Optional[str]


@dataclass
class ListingHistoryEntry:
    listing_id: str
    timestamp_iso: str
    price_usdc: Optional[float]
    ipfs_cid: Optional[str]
    purchase_count: int
    insight_preview: Optional[str]


@dataclass
class SellerProfileResponse:
    seller_wallet: str
    display_name: str
    seller_stats: SellerStats
    reputation_score_effective: int
    reputation_score_raw: int
    decay_info: DecayInfo
    registered_agent_name: Optional[str]
    registered_agent_role: Optional[str]
    registered_at_round: Optional[int]
    reputation_history: list[dict[str, Any]]
    trust_summary: str

    @property
    def total_purchases(self) -> int:
        return int(self.seller_stats.total_purchases or 0)

    @property
    def total_usdc_earned_micro(self) -> float:
        return float(self.seller_stats.total_usdc_earned_micro or 0.0)

    @property
    def avg_price_usdc(self) -> Optional[float]:
        return self.seller_stats.avg_price_usdc


def _db_connection(db_path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or str(get_db_path()))
    conn.row_factory = sqlite3.Row
    return conn


def _default_stats(wallet: str) -> SellerStats:
    return SellerStats(
        seller_wallet=wallet,
        total_purchases=0,
        total_usdc_earned_micro=0.0,
        avg_price_usdc=None,
        first_listing_date=None,
        last_purchase_date=None,
        recent_evaluations_avg_score=None,
        display_name="",
        registered_agent_name=None,
        registered_agent_role=None,
        registered_at_round=None,
        trust_summary=None,
    )


class SellerProfileService:
    def __init__(self, algod_client: Any, indexer_client: Any, db_path: str | None = None) -> None:
        self.algod_client = algod_client
        self.indexer_client = indexer_client
        self.db_path = db_path
        initialise_seller_profile_schema()

# Module-level caches for hot-path seller lookups
_profile_cache: TTLCache = TTLCache(maxsize=200, ttl=30)
_reputation_cache: TTLCache = TTLCache(maxsize=200, ttl=30)


def invalidate_profile_cache(wallet: str) -> None:
    """Invalidate cached seller profile for `wallet`."""
    try:
        _profile_cache.pop(wallet, None)
    except Exception:
        pass


def invalidate_reputation_cache(wallet: str) -> None:
    try:
        _reputation_cache.pop(wallet, None)
    except Exception:
        pass

    async def get_profile_tier1_tier2(self, wallet: str) -> SellerProfileResponse:
        # Return cached profile when available to reduce indexer/sqlite load
        cached = _profile_cache.get(wallet)
        if cached is not None:
            return cached

        sqlite_task = asyncio.create_task(self._fetch_sqlite_stats(wallet))
        onchain_task = asyncio.create_task(self._fetch_onchain_profile(wallet))
        sqlite_result, onchain_result = await asyncio.gather(sqlite_task, onchain_task)

        stats: SellerStats = sqlite_result["stats"]
        merged_stats = SellerStats(
            seller_wallet=wallet,
            total_purchases=stats.total_purchases,
            total_usdc_earned_micro=stats.total_usdc_earned_micro,
            avg_price_usdc=stats.avg_price_usdc,
            first_listing_date=stats.first_listing_date,
            last_purchase_date=stats.last_purchase_date,
            recent_evaluations_avg_score=stats.recent_evaluations_avg_score,
            display_name=onchain_result.get("display_name") or stats.display_name,
            registered_agent_name=onchain_result.get("registered_agent_name"),
            registered_agent_role=onchain_result.get("registered_agent_role"),
            registered_at_round=onchain_result.get("registered_at_round"),
            trust_summary=stats.trust_summary,
        )

        response = SellerProfileResponse(
            seller_wallet=wallet,
            display_name=merged_stats.display_name,
            seller_stats=merged_stats,
            reputation_score_effective=onchain_result.get("reputation_score_effective", 0),
            reputation_score_raw=onchain_result.get("reputation_score_raw", 0),
            decay_info=onchain_result.get("decay_info")
            or DecayInfo(last_updated_at=None, decay_rate=None, decay_points_applied=0),
            registered_agent_name=onchain_result.get("registered_agent_name"),
            registered_agent_role=onchain_result.get("registered_agent_role"),
            registered_at_round=onchain_result.get("registered_at_round"),
            reputation_history=sqlite_result["reputation_history"],
            trust_summary=stats.trust_summary or "",
        )

        response.trust_summary = await build_trust_summary(response)
        try:
            _profile_cache[wallet] = response
        except Exception:
            pass
        return response

    async def _fetch_sqlite_stats(self, wallet: str) -> dict[str, Any]:
        def _query() -> dict[str, Any]:
            conn = _db_connection(self.db_path)
            try:
                stats_row = conn.execute(
                    "SELECT * FROM seller_stats WHERE seller_wallet = ?",
                    (wallet,),
                ).fetchone()

                reputation_rows = conn.execute(
                    "SELECT history_id, seller_wallet, score_before, score_after, change, triggered_by_listing_id, recorded_at FROM reputation_score_history WHERE seller_wallet = ? ORDER BY recorded_at DESC LIMIT 20",
                    (wallet,),
                ).fetchall()

                avg_eval_row = conn.execute(
                    "SELECT AVG(total_score) AS avg_eval_score FROM evaluations WHERE seller_wallet = ?",
                    (wallet,),
                ).fetchone()

                cached_summary = conn.execute(
                    "SELECT trust_summary FROM seller_trust_summary_cache WHERE seller_wallet = ?",
                    (wallet,),
                ).fetchone()
            finally:
                conn.close()

            if stats_row is None:
                stats = _default_stats(wallet)
            else:
                stats = SellerStats(
                    seller_wallet=wallet,
                    total_purchases=int(stats_row["total_purchases"] or 0),
                    total_usdc_earned_micro=float(stats_row["total_usdc_earned"] or 0.0),
                    avg_price_usdc=(float(stats_row["avg_price_usdc"]) if stats_row["avg_price_usdc"] is not None else None),
                    first_listing_date=stats_row["first_listing_date"],
                    last_purchase_date=stats_row["last_purchase_date"],
                    recent_evaluations_avg_score=(float(avg_eval_row["avg_eval_score"]) if avg_eval_row and avg_eval_row["avg_eval_score"] is not None else None),
                    display_name="",
                    registered_agent_name=None,
                    registered_agent_role=None,
                    registered_at_round=None,
                    trust_summary=(cached_summary["trust_summary"] if cached_summary else None),
                )

            reputation_history = [dict(row) for row in reputation_rows]
            return {"stats": stats, "reputation_history": reputation_history}

        return await asyncio.to_thread(_query)

    async def _fetch_onchain_profile(self, wallet: str) -> dict[str, Any]:
        reputation_task = asyncio.create_task(self._read_box_json("REPUTATION_APP_ID", wallet, prefix=b"rep_"))
        agent_task = asyncio.create_task(self._read_box_json("AGENT_REGISTRY_APP_ID", wallet, prefix=b"agent_"))
        reputation_box, agent_box = await asyncio.gather(reputation_task, agent_task)

        return {
            "reputation_score_effective": reputation_box.get("reputation_score_effective", 0),
            "reputation_score_raw": reputation_box.get("reputation_score_raw", 0),
            "decay_info": reputation_box.get("decay_info"),
            "display_name": agent_box.get("display_name") or "",
            "registered_agent_name": agent_box.get("registered_agent_name"),
            "registered_agent_role": agent_box.get("registered_agent_role"),
            "registered_at_round": agent_box.get("registered_at_round"),
        }

    async def _read_box_json(self, app_id_env: str, wallet: str, prefix: bytes) -> dict[str, Any]:
        app_id = int(os.getenv(app_id_env, "0") or 0)
        if app_id <= 0:
            return {}

        if algo_encoding is not None:
            try:
                key_bytes = prefix + algo_encoding.decode_address(wallet)
            except Exception:
                key_bytes = prefix
        else:
            key_bytes = prefix

        raw_bytes = await self._read_box_raw(app_id, key_bytes)
        if not raw_bytes:
            return {}
        return self._deserialise_seller_record(raw_bytes)

    def _indexer_base_url(self) -> str:
        candidates = [
            os.getenv("INDEXER_URL", ""),
            os.getenv("INDEXER_SERVER", ""),
            getattr(self.indexer_client, "indexer_address", ""),
            getattr(self.indexer_client, "host", ""),
            getattr(self.indexer_client, "address", ""),
        ]
        for candidate in candidates:
            if candidate:
                return str(candidate)
        return ""

    def _indexer_token(self) -> str:
        candidates = [
            os.getenv("INDEXER_TOKEN", ""),
            os.getenv("ALGOD_TOKEN", ""),
            getattr(self.indexer_client, "indexer_token", ""),
            getattr(self.indexer_client, "token", ""),
        ]
        for candidate in candidates:
            if candidate:
                return str(candidate)
        return ""

    async def _read_box_raw(self, app_id: int, key_bytes: bytes) -> Optional[bytes]:
        base_url = self._indexer_base_url().rstrip("/")
        if not base_url:
            return None

        key_b64 = base64.b64encode(key_bytes).decode("ascii")
        url_key = quote(key_b64, safe="")
        url = f"{base_url}/v2/applications/{app_id}/box/{url_key}"
        headers = {}
        token = self._indexer_token()
        if token:
            headers["X-Indexer-API-Token"] = token

        from backend.utils.http_client import get_http_client

        client = await get_http_client()
        r = await client.get(url, headers=headers, timeout=10.0)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        payload = r.json() if r.content else {}
        value = payload.get("value")
        if not value and isinstance(payload.get("box"), dict):
            value = payload["box"].get("value")
        if not value:
            return None
        return base64.b64decode(value)

    def _deserialise_seller_record(self, raw_bytes: bytes) -> dict[str, Any]:
        position = 0

        def read_u64() -> int:
            nonlocal position
            if position + 8 > len(raw_bytes):
                return 0
            value = int.from_bytes(raw_bytes[position : position + 8], "big")
            position += 8
            return value

        def read_address() -> Optional[str]:
            nonlocal position
            if position + 32 > len(raw_bytes):
                return None
            addr_bytes = raw_bytes[position : position + 32]
            position += 32
            if algo_encoding is None:
                return None
            try:
                return algo_encoding.encode_address(addr_bytes)
            except Exception:
                return None

        def read_string() -> Optional[str]:
            nonlocal position
            if position + 2 > len(raw_bytes):
                return None
            length = int.from_bytes(raw_bytes[position : position + 2], "big")
            position += 2
            if position + length > len(raw_bytes):
                return None
            value = raw_bytes[position : position + length].decode("utf-8", errors="replace")
            position += length
            return value

        record: dict[str, Any] = {
            "reputation_score_raw": read_u64(),
            "reputation_score_effective": read_u64(),
            "registered_at_round": read_u64(),
            "score_before": read_u64(),
            "seller_address": read_address(),
            "display_name": read_string() or "",
            "registered_agent_name": read_string(),
            "registered_agent_role": read_string(),
        }

        if position + 8 <= len(raw_bytes):
            record["decay_info"] = DecayInfo(
                last_updated_at=datetime.now(timezone.utc).isoformat(),
                decay_rate=None,
                decay_points_applied=0,
            )
        else:
            record["decay_info"] = DecayInfo(last_updated_at=None, decay_rate=None, decay_points_applied=0)

        return record

    async def get_listing_history(self, wallet: str, page: int = 1, page_size: int = 10) -> dict[str, Any]:
        page = max(1, page)
        page_size = max(1, min(page_size, 50))
        offset = (page - 1) * page_size

        def _query() -> tuple[list[dict[str, Any]], int]:
            conn = _db_connection(self.db_path)
            try:
                rows = conn.execute(
                    """
                    SELECT DISTINCT
                        json_extract(metadata, '$.listing_id') AS listing_id,
                        timestamp_iso,
                        json_extract(metadata, '$.price_usdc') AS price_usdc,
                        json_extract(metadata, '$.ipfs_cid') AS cid
                    FROM flow_events
                    WHERE event_name = 'listing.asa_creation_completed' AND wallet_involved = ?
                    ORDER BY timestamp_iso DESC
                    LIMIT ? OFFSET ?
                    """,
                    (wallet, page_size, offset),
                ).fetchall()
                total_row = conn.execute(
                    """
                    SELECT COUNT(DISTINCT json_extract(metadata, '$.listing_id')) AS total_count
                    FROM flow_events
                    WHERE event_name = 'listing.asa_creation_completed' AND wallet_involved = ?
                    """,
                    (wallet,),
                ).fetchone()
            finally:
                conn.close()

            return [dict(row) for row in rows], int(total_row["total_count"] or 0)

        rows, total_count = await asyncio.to_thread(_query)

        async def _purchase_count(listing_id: str) -> int:
            def _count() -> int:
                conn = _db_connection(self.db_path)
                try:
                    row = conn.execute(
                        """
                        SELECT COUNT(*) AS purchase_count
                        FROM flow_events
                        WHERE event_name = 'escrow.release_completed' AND json_extract(metadata, '$.listing_id') = ?
                        """,
                        (listing_id,),
                    ).fetchone()
                finally:
                    conn.close()
                return int(row["purchase_count"] or 0)

            return await asyncio.to_thread(_count)

        purchase_counts = await asyncio.gather(*[_purchase_count(str(row["listing_id"])) for row in rows]) if rows else []

        now = datetime.now(timezone.utc)
        listings: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            created_at = row.get("timestamp_iso")
            preview = None
            if row.get("cid") and created_at:
                try:
                    created_dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                    if now - created_dt <= timedelta(days=7):
                        preview = await asyncio.to_thread(
                            self._fetch_insight_preview,
                            str(row["cid"]),
                        )
                except Exception:
                    preview = None

            entry = ListingHistoryEntry(
                listing_id=str(row.get("listing_id") or ""),
                timestamp_iso=str(created_at or ""),
                price_usdc=(float(row["price_usdc"]) if row.get("price_usdc") is not None else None),
                ipfs_cid=row.get("cid"),
                purchase_count=purchase_counts[index] if index < len(purchase_counts) else 0,
                insight_preview=preview,
            )
            listings.append(asdict(entry))

        return {
            "listings": listings,
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "has_more": page * page_size < total_count,
            "total_pages": math.ceil(total_count / page_size) if page_size else 0,
        }

    def _fetch_insight_preview(self, cid: str) -> Optional[str]:
        if not cid:
            return None
        try:
            from backend.utils.ipfs import fetch_insight_from_ipfs

            return fetch_insight_from_ipfs(cid)
        except Exception:
            return None


async def build_trust_summary(profile: SellerProfileResponse) -> str:
    stats = profile.seller_stats
    name = stats.display_name.strip() or profile.registered_agent_name or profile.seller_wallet[:8]
    score = int(profile.reputation_score_effective or 0)
    category = "top tier" if score >= 80 else "trusted" if score >= 70 else "standard" if score >= 50 else "developing"

    first_sentence = (
        f"{name} has sold {stats.total_purchases} insight(s) with a reputation score of {score}/100, placing them in the {category} seller category."
    )
    if (profile.registered_agent_role or "").lower() == "curator":
        first_sentence = (
            "This is Mercator's automated Curator Agent, which publishes AI-synthesised market insights from live NSE/BSE data. "
            + first_sentence
        )

    avg_eval_score = stats.recent_evaluations_avg_score
    if avg_eval_score is not None and avg_eval_score >= 75:
        second_sentence = (
            f"The Buyer Agent has consistently rated their insights as high-quality with an average evaluation score of {avg_eval_score:.0f}/100."
        )
    elif avg_eval_score is not None and avg_eval_score >= 50:
        second_sentence = "The Buyer Agent rates their insights as moderate quality on average."
    else:
        second_sentence = "This seller has limited evaluation history — exercise judgment before purchasing."

    summary = f"{first_sentence} {second_sentence}"

    def _cache_summary() -> None:
        conn = _db_connection()
        try:
            conn.execute(
                """
                INSERT INTO seller_trust_summary_cache (seller_wallet, trust_summary, reputation_score, avg_eval_score, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(seller_wallet) DO UPDATE SET
                    trust_summary = excluded.trust_summary,
                    reputation_score = excluded.reputation_score,
                    avg_eval_score = excluded.avg_eval_score,
                    updated_at = excluded.updated_at
                """,
                (
                    profile.seller_wallet,
                    summary,
                    score,
                    avg_eval_score,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    await asyncio.to_thread(_cache_summary)
    return summary
