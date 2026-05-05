"""SQLite helpers for Mercator curator runtime state."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .runtime_env import repo_root


def _db_path() -> Path:
    configured = os.getenv("CURATOR_DB_PATH", "").strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            return repo_root() / path
        return path
    return repo_root() / "mercator.db"


def get_db_path() -> Path:
    return _db_path()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def initialise_curator_schema() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS curator_runs (
                run_id TEXT PRIMARY KEY,
                run_started_at TEXT,
                run_completed_at TEXT,
                symbol TEXT,
                snapshot_quality_score INTEGER,
                volume_ratio REAL,
                price_change_pct REAL,
                headlines_found INTEGER,
                synthesis_quality TEXT,
                confidence_score INTEGER,
                directional_view TEXT,
                insight_text TEXT,
                price_usdc REAL,
                published INTEGER,
                skip_reason TEXT,
                listing_tx_id TEXT,
                listing_ipfs_cid TEXT,
                error TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS curator_run_errors (
                error_id TEXT PRIMARY KEY,
                run_id TEXT,
                error_type TEXT,
                error_detail TEXT,
                occurred_at TEXT
            )
            """
        )
        conn.commit()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_curator_run(row: dict[str, Any]) -> None:
    initialise_curator_schema()
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO curator_runs (
                run_id,
                run_started_at,
                run_completed_at,
                symbol,
                snapshot_quality_score,
                volume_ratio,
                price_change_pct,
                headlines_found,
                synthesis_quality,
                confidence_score,
                directional_view,
                insight_text,
                price_usdc,
                published,
                skip_reason,
                listing_tx_id,
                listing_ipfs_cid,
                error
            ) VALUES (
                :run_id,
                :run_started_at,
                :run_completed_at,
                :symbol,
                :snapshot_quality_score,
                :volume_ratio,
                :price_change_pct,
                :headlines_found,
                :synthesis_quality,
                :confidence_score,
                :directional_view,
                :insight_text,
                :price_usdc,
                :published,
                :skip_reason,
                :listing_tx_id,
                :listing_ipfs_cid,
                :error
            )
            """,
            row,
        )
        conn.commit()


def record_curator_error(row: dict[str, Any]) -> None:
    initialise_curator_schema()
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO curator_run_errors (
                error_id,
                run_id,
                error_type,
                error_detail,
                occurred_at
            ) VALUES (
                :error_id,
                :run_id,
                :error_type,
                :error_detail,
                :occurred_at
            )
            """,
            row,
        )
        conn.commit()


def fetch_curator_recent_runs(limit: int = 5) -> list[dict[str, Any]]:
    initialise_curator_schema()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT symbol, published, skip_reason, confidence_score, listing_tx_id, run_completed_at
            FROM curator_runs
            ORDER BY run_started_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_curator_today_stats(now: datetime | None = None) -> dict[str, int]:
    initialise_curator_schema()
    current = now or datetime.now(timezone.utc)
    start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta

    day_end = start + timedelta(days=1)
    with _connect() as conn:
        total_runs = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM curator_runs
            WHERE run_started_at >= ? AND run_started_at < ?
            """,
            (start.isoformat(), day_end.isoformat()),
        ).fetchone()["count"]
        successful_publishes = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM curator_runs
            WHERE run_started_at >= ? AND run_started_at < ? AND published = 1
            """,
            (start.isoformat(), day_end.isoformat()),
        ).fetchone()["count"]
        skipped_low_quality = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM curator_runs
            WHERE run_started_at >= ? AND run_started_at < ? AND published = 0 AND skip_reason LIKE 'data_quality_score%'
            """,
            (start.isoformat(), day_end.isoformat()),
        ).fetchone()["count"]
        errors = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM curator_run_errors
            WHERE occurred_at >= ? AND occurred_at < ?
            """,
            (start.isoformat(), day_end.isoformat()),
        ).fetchone()["count"]
        total_insights_published_today = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM curator_runs
            WHERE run_started_at >= ? AND run_started_at < ? AND published = 1
            """,
            (start.isoformat(), day_end.isoformat()),
        ).fetchone()["count"]

    return {
        "total_runs": int(total_runs or 0),
        "successful_publishes": int(successful_publishes or 0),
        "skipped_low_quality": int(skipped_low_quality or 0),
        "errors": int(errors or 0),
        "total_insights_published_today": int(total_insights_published_today or 0),
    }
