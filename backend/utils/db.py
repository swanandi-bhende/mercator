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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                email_hash TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                algo_address TEXT UNIQUE NOT NULL,
                encrypted_mnemonic TEXT NOT NULL,
                pbkdf2_salt TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_active_at TEXT,
                onboarding_complete INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                key_id TEXT PRIMARY KEY,
                key_hash TEXT UNIQUE NOT NULL,
                owner_name TEXT NOT NULL,
                owner_email TEXT NOT NULL,
                tier TEXT NOT NULL DEFAULT 'developer',
                rate_limit_per_minute INTEGER NOT NULL DEFAULT 60,
                created_at TEXT NOT NULL,
                last_used_at TEXT,
                total_requests INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_request_log (
                request_id TEXT PRIMARY KEY,
                key_id TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                method TEXT NOT NULL,
                request_body_summary TEXT,
                response_status INTEGER,
                response_time_ms INTEGER,
                requested_at TEXT NOT NULL,
                ip_address TEXT
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


def initialise_evaluations_schema() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evaluations (
                evaluation_id TEXT PRIMARY KEY,
                session_id TEXT,
                listing_id TEXT,
                seller_wallet TEXT,
                query TEXT,
                reputation_score_at_eval INTEGER,
                price_usdc_at_eval REAL,
                step1_relevance_score INTEGER,
                step1_evidence TEXT,
                step2_reputation_score INTEGER,
                step2_evidence TEXT,
                step3_value_score INTEGER,
                step3_evidence TEXT,
                step4_specificity_score INTEGER,
                step4_evidence TEXT,
                total_score INTEGER,
                buy_confidence INTEGER,
                decision TEXT,
                decision_reasoning TEXT,
                improvement_suggestion TEXT,
                evaluation_version TEXT,
                gemini_call_count INTEGER,
                evaluated_at TEXT,
                duration_ms INTEGER
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_evaluations_listing_id ON evaluations(listing_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_evaluations_evaluated_at ON evaluations(evaluated_at)")
        conn.commit()
    conn.commit()


def record_evaluation(row: dict[str, Any]) -> None:
    initialise_evaluations_schema()
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO evaluations (
                evaluation_id,
                session_id,
                listing_id,
                seller_wallet,
                query,
                reputation_score_at_eval,
                price_usdc_at_eval,
                step1_relevance_score,
                step1_evidence,
                step2_reputation_score,
                step2_evidence,
                step3_value_score,
                step3_evidence,
                step4_specificity_score,
                step4_evidence,
                total_score,
                buy_confidence,
                decision,
                decision_reasoning,
                improvement_suggestion,
                evaluation_version,
                gemini_call_count,
                evaluated_at,
                duration_ms
            ) VALUES (
                :evaluation_id,
                :session_id,
                :listing_id,
                :seller_wallet,
                :query,
                :reputation_score_at_eval,
                :price_usdc_at_eval,
                :step1_relevance_score,
                :step1_evidence,
                :step2_reputation_score,
                :step2_evidence,
                :step3_value_score,
                :step3_evidence,
                :step4_specificity_score,
                :step4_evidence,
                :total_score,
                :buy_confidence,
                :decision,
                :decision_reasoning,
                :improvement_suggestion,
                :evaluation_version,
                :gemini_call_count,
                :evaluated_at,
                :duration_ms
            )
            """,
            row,
        )
        conn.commit()


def fetch_evaluations_history(limit: int = 20, decision: str | None = None) -> list[dict[str, Any]]:
    initialise_evaluations_schema()
    with _connect() as conn:
        if decision and decision.lower() != "all":
            rows = conn.execute(
                "SELECT * FROM evaluations WHERE decision = ? ORDER BY evaluated_at DESC LIMIT ?",
                (decision.upper(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM evaluations ORDER BY evaluated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


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


def initialise_listing_preparation_schema() -> None:
    """Create listing_preparation_log table for IPFS two-phase audit trail.
    
    Purpose: Track all listing creation attempts, whether they succeed or fail at
    simulation or execution. Provides complete audit trail for IPFS orphan cleanup.
    
    Columns:
    - preparation_id: Unique identifier for this attempt (UUID)
    - cid_pinned: The IPFS CID that was pinned (NULL if pin failed)
    - simulation_success: True if ASA creation simulation passed
    - execution_success: True if ASA creation executed successfully
    - simulation_error: Error message if simulation failed
    - execution_tx_id: On-chain transaction ID if execution succeeded
    - created_at: ISO 8601 timestamp when preparation started
    """
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS listing_preparation_log (
                preparation_id TEXT PRIMARY KEY,
                seller_wallet TEXT NOT NULL,
                cid_pinned TEXT,
                simulation_success INTEGER DEFAULT 0,
                execution_success INTEGER DEFAULT 0,
                simulation_error TEXT,
                execution_error TEXT,
                execution_tx_id TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_listing_prep_seller ON listing_preparation_log(seller_wallet)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_listing_prep_cid ON listing_preparation_log(cid_pinned)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_listing_prep_created ON listing_preparation_log(created_at)")
        conn.commit()


def log_listing_preparation_start(
    preparation_id: str,
    seller_wallet: str,
    cid: str | None = None,
) -> None:
    """Log the start of a listing preparation attempt.
    
    Args:
        preparation_id: Unique ID for this preparation attempt
        seller_wallet: Seller's Algorand address
        cid: IPFS CID if IPFS upload succeeded, None if not yet uploaded
    """
    initialise_listing_preparation_schema()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO listing_preparation_log (
                preparation_id,
                seller_wallet,
                cid_pinned,
                created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (preparation_id, seller_wallet, cid, _utc_now_iso()),
        )
        conn.commit()


def log_listing_simulation_failure(
    preparation_id: str,
    error_message: str,
) -> None:
    """Log a simulation failure for a preparation attempt.
    
    Args:
        preparation_id: Unique ID for this preparation attempt
        error_message: Simulation failure reason
    """
    with _connect() as conn:
        conn.execute(
            """
            UPDATE listing_preparation_log
            SET simulation_success = 0, simulation_error = ?
            WHERE preparation_id = ?
            """,
            (error_message, preparation_id),
        )
        conn.commit()


def log_listing_execution_result(
    preparation_id: str,
    success: bool,
    tx_id: str | None = None,
    error_message: str | None = None,
) -> None:
    """Log the execution result (success or failure) for a preparation attempt.
    
    Args:
        preparation_id: Unique ID for this preparation attempt
        success: True if execution succeeded
        tx_id: Transaction ID if execution succeeded
        error_message: Error message if execution failed
    """
    with _connect() as conn:
        conn.execute(
            """
            UPDATE listing_preparation_log
            SET simulation_success = 1, execution_success = ?, execution_tx_id = ?, execution_error = ?
            WHERE preparation_id = ?
            """,
            (1 if success else 0, tx_id, error_message, preparation_id),
        )
        conn.commit()
