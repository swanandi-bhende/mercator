from __future__ import annotations

import asyncio
import csv
import json
import logging
import sqlite3
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from backend.utils.ws_manager import ws_manager
except Exception:  # pragma: no cover - avoid hard-failing in test contexts
    ws_manager = None


logger = logging.getLogger(__name__)


VALID_STATUSES: frozenset[str] = frozenset({"pending", "success", "failure", "skipped"})

VALID_EVENT_NAMES: frozenset[str] = frozenset(
    {
        # ipfs
        "ipfs.upload_started",
        "ipfs.upload_completed",
        "ipfs.upload_failed",
        "ipfs.fetch_started",
        "ipfs.fetch_completed",
        "ipfs.fetch_failed",
        # listing
        "listing.validation_passed",
        "listing.asa_creation_started",
        "listing.asa_creation_completed",
        "listing.asa_creation_failed",
        "listing.expired",
        "listing.sold",
        "listing.subscriber_access_granted",
        # agent
        "agent.search_started",
        "agent.search_completed",
        "agent.evaluation_started",
        "agent.evaluation_completed",
        "agent.auto_approval_check",
        "agent.auto_approved",
        "agent.auto_rejected",
        "agent.manual_approval_requested",
        "agent.manual_approved",
        "agent.manual_rejected",
        # payment
        "payment.simulation_started",
        "payment.simulation_passed",
        "payment.simulation_failed",
        "payment.broadcast_started",
        "payment.broadcast_completed",
        "payment.broadcast_failed",
        "payment.subscription_check",
        "payment.subscription_used",
        # escrow
        "escrow.release_started",
        "escrow.release_completed",
        "escrow.release_failed",
        "escrow.subscriber_release_started",
        "escrow.subscriber_release_completed",
        # reputation
        "reputation.update_started",
        "reputation.update_completed",
        "reputation.score_read",
        # curator
        "curator.cycle_started",
        "curator.data_fetched",
        "curator.synthesis_completed",
        "curator.publish_started",
        "curator.publish_completed",
        "curator.publish_skipped",
        # session
        "session.started",
        "session.completed",
        "session.exported",
    }
)


@dataclass(frozen=True)
class FlowEvent:
    event_id: str
    session_id: str
    event_name: str
    timestamp_iso: str
    status: str
    duration_ms: Optional[int] = field(default=None)
    wallet_involved: Optional[str] = field(default=None)
    tx_id: Optional[str] = field(default=None)
    ipfs_cid: Optional[str] = field(default=None)
    error_code: Optional[str] = field(default=None)
    error_message: Optional[str] = field(default=None)
    plain_english_description: str = field(default="")
    metadata: Optional[dict] = field(default=None)


_session_id_var: ContextVar[Optional[str]] = ContextVar("session_id", default=None)
_session_start_time_var: ContextVar[Optional[float]] = ContextVar("session_start_time", default=None)


class FlowTracer:
    def __init__(self, db_path: str, traces_dir: str) -> None:
        self.db_path = Path(db_path)
        self.traces_dir = Path(traces_dir)
        self._pending_events: dict[str, float] = {}
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.traces_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS flow_events (
                    event_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    event_name TEXT NOT NULL,
                    timestamp_iso TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration_ms INTEGER,
                    wallet_involved TEXT,
                    tx_id TEXT,
                    ipfs_cid TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    plain_english_description TEXT NOT NULL,
                    metadata TEXT,
                    exported INTEGER DEFAULT 0
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_flow_events_session_id ON flow_events(session_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_flow_events_event_name ON flow_events(event_name)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_flow_events_timestamp_iso ON flow_events(timestamp_iso)"
            )
            conn.commit()
        finally:
            conn.close()

    def start_session(self, session_type: str = "buyer_purchase") -> str:
        new_id = str(uuid.uuid4())
        _session_id_var.set(new_id)
        _session_start_time_var.set(time.monotonic())
        self.record(
            "session.started",
            "success",
            plain_english_description=f"New {session_type} session started",
            metadata={"session_type": session_type},
        )
        return new_id

    def get_current_session_id(self) -> Optional[str]:
        return _session_id_var.get(None)

    def record(
        self,
        event_name: str,
        status: str,
        *,
        wallet_involved: Optional[str] = None,
        tx_id: Optional[str] = None,
        ipfs_cid: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        plain_english_description: str,
        duration_ms: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[FlowEvent]:
        session_id = _session_id_var.get(None)
        if session_id is None:
            logger.warning("FlowTracer.record() called outside of a session - event discarded")
            return None

        if event_name not in VALID_EVENT_NAMES:
            logger.warning(
                "Unknown event name '%s' - did you forget to add it to VALID_EVENT_NAMES?",
                event_name,
            )

        if status not in VALID_STATUSES:
            logger.warning("Invalid status '%s' for event '%s'; coercing to 'failure'", status, event_name)
            status = "failure"

        event = FlowEvent(
            event_id=str(uuid.uuid4()),
            session_id=session_id,
            event_name=event_name,
            timestamp_iso=datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            status=status,
            duration_ms=duration_ms,
            wallet_involved=wallet_involved,
            tx_id=tx_id,
            ipfs_cid=ipfs_cid,
            error_code=error_code,
            error_message=error_message,
            plain_english_description=plain_english_description,
            metadata=metadata,
        )

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO flow_events (
                        event_id,
                        session_id,
                        event_name,
                        timestamp_iso,
                        status,
                        duration_ms,
                        wallet_involved,
                        tx_id,
                        ipfs_cid,
                        error_code,
                        error_message,
                        plain_english_description,
                        metadata,
                        exported
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        event.event_id,
                        event.session_id,
                        event.event_name,
                        event.timestamp_iso,
                        event.status,
                        event.duration_ms,
                        event.wallet_involved,
                        event.tx_id,
                        event.ipfs_cid,
                        event.error_code,
                        event.error_message,
                        event.plain_english_description,
                        json.dumps(event.metadata) if event.metadata is not None else None,
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to persist flow event '%s': %s", event_name, exc)

        if metadata:
            logger.debug("Flow event metadata for '%s': %s", event_name, metadata)

        if ws_manager is not None:
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(ws_manager.broadcast("flow_event", event.__dict__))
            except Exception as exc:  # noqa: BLE001
                logger.debug("Flow event websocket broadcast skipped: %s", exc)

        return event

    def start_event(
        self,
        event_name: str,
        *,
        wallet_involved: Optional[str] = None,
        plain_english_description: str,
        metadata: Optional[dict] = None,
    ) -> str:
        pending_event = self.record(
            event_name,
            "pending",
            wallet_involved=wallet_involved,
            plain_english_description=plain_english_description,
            metadata=metadata,
        )
        if pending_event is None:
            return ""
        self._pending_events[pending_event.event_id] = time.monotonic()
        return pending_event.event_id

    def resolve_event(
        self,
        event_id: str,
        status: str,
        *,
        tx_id: Optional[str] = None,
        ipfs_cid: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        plain_english_description: str,
        metadata: Optional[dict] = None,
    ) -> Optional[FlowEvent]:
        start_time = self._pending_events.pop(event_id, None)
        duration_ms: Optional[int] = None
        if start_time is None:
            logger.warning("FlowTracer.resolve_event() called with unknown event_id '%s'", event_id)
        else:
            duration_ms = int((time.monotonic() - start_time) * 1000)

        original_event_name = "unknown.event"
        original_wallet = None
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT event_name, wallet_involved FROM flow_events WHERE event_id = ? LIMIT 1",
                (event_id,),
            ).fetchone()
            if row is not None:
                original_event_name = str(row[0])
                original_wallet = row[1]

        return self.record(
            event_name=original_event_name,
            status=status,
            wallet_involved=original_wallet,
            tx_id=tx_id,
            ipfs_cid=ipfs_cid,
            error_code=error_code,
            error_message=error_message,
            plain_english_description=plain_english_description,
            duration_ms=duration_ms,
            metadata=metadata,
        )

    def _parse_timestamp(self, value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def export_json(self, session_id: Optional[str] = None) -> Path:
        resolved_id = session_id or _session_id_var.get(None)
        if resolved_id is None:
            raise ValueError("No session_id provided and no active session in context")

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM flow_events WHERE session_id = ? ORDER BY timestamp_iso ASC",
                (resolved_id,),
            ).fetchall()

            events: list[dict[str, object]] = []
            for row in rows:
                row_dict = dict(row)
                metadata_raw = row_dict.get("metadata")
                if isinstance(metadata_raw, str) and metadata_raw:
                    try:
                        row_dict["metadata"] = json.loads(metadata_raw)
                    except Exception:
                        row_dict["metadata"] = metadata_raw
                events.append(row_dict)

            success_count = sum(1 for event in events if event.get("status") == "success")
            failure_count = sum(1 for event in events if event.get("status") == "failure")
            skipped_count = sum(1 for event in events if event.get("status") == "skipped")

            session_duration_ms = 0
            if events:
                started_at = self._parse_timestamp(str(events[0]["timestamp_iso"]))
                ended_at = self._parse_timestamp(str(events[-1]["timestamp_iso"]))
                session_duration_ms = int((ended_at - started_at).total_seconds() * 1000)

            export_dict = {
                "export_version": "1.0",
                "session_id": resolved_id,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "total_events": len(events),
                "session_duration_ms": session_duration_ms,
                "success_count": success_count,
                "failure_count": failure_count,
                "skipped_count": skipped_count,
                "events": events,
            }

            path = self.traces_dir / f"flow_trace_{resolved_id}.json"
            path.write_text(json.dumps(export_dict, indent=2), encoding="utf-8")

            conn.execute(
                "UPDATE flow_events SET exported = 1 WHERE session_id = ?",
                (resolved_id,),
            )

        token = _session_id_var.set(resolved_id)
        try:
            self.record(
                "session.exported",
                "success",
                plain_english_description=f"Session {resolved_id} exported to JSON",
                metadata={"session_id": resolved_id, "format": "json", "path": str(path)},
            )
        finally:
            _session_id_var.reset(token)
        return path

    def export_csv(self, session_id: Optional[str] = None) -> Path:
        resolved_id = session_id or _session_id_var.get(None)
        if resolved_id is None:
            raise ValueError("No session_id provided and no active session in context")

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM flow_events WHERE session_id = ? ORDER BY timestamp_iso ASC",
                (resolved_id,),
            ).fetchall()

            events = [dict(row) for row in rows]
            for event in events:
                metadata_raw = event.get("metadata")
                if isinstance(metadata_raw, str) and metadata_raw:
                    try:
                        metadata_obj = json.loads(metadata_raw)
                        event["metadata"] = json.dumps(metadata_obj)
                    except Exception:
                        event["metadata"] = metadata_raw

            conn.execute(
                "UPDATE flow_events SET exported = 1 WHERE session_id = ?",
                (resolved_id,),
            )

        path = self.traces_dir / f"flow_trace_{resolved_id}.csv"
        fieldnames = [
            "event_id",
            "session_id",
            "event_name",
            "timestamp_iso",
            "status",
            "duration_ms",
            "wallet_involved",
            "tx_id",
            "ipfs_cid",
            "error_code",
            "error_message",
            "plain_english_description",
            "metadata",
            "exported",
        ]

        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            for event in events:
                writer.writerow({key: event.get(key) for key in fieldnames})

        token = _session_id_var.set(resolved_id)
        try:
            self.record(
                "session.exported",
                "success",
                plain_english_description=f"Session {resolved_id} exported to CSV",
                metadata={"session_id": resolved_id, "format": "csv", "path": str(path)},
            )
        finally:
            _session_id_var.reset(token)
        return path

    def export_session_json(self, session_id: str) -> str:
        return str(self.export_json(session_id))

    def get_events(
        self,
        session_id: str,
        status: Optional[str] = None,
        event_name: Optional[str] = None,
    ) -> list[dict[str, object]]:
        query = "SELECT * FROM flow_events WHERE session_id = ?"
        params: list[object] = [session_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        if event_name:
            query += " AND event_name = ?"
            params.append(event_name)
        query += " ORDER BY timestamp_iso ASC"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, tuple(params)).fetchall()

        events = [dict(row) for row in rows]
        for event in events:
            metadata_raw = event.get("metadata")
            if isinstance(metadata_raw, str) and metadata_raw:
                try:
                    event["metadata"] = json.loads(metadata_raw)
                except Exception:
                    event["metadata"] = metadata_raw
        return events

    def get_recent_sessions(self, limit: int = 20) -> list[dict[str, object]]:
        safe_limit = max(1, min(limit, 200))
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT DISTINCT session_id, MAX(timestamp_iso) AS last_event, COUNT(*) AS event_count
                FROM flow_events
                GROUP BY session_id
                ORDER BY last_event DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_session_summary(self, session_id: str) -> dict[str, object]:
        events = self.get_events(session_id)
        total_events = len(events)
        success_count = sum(1 for event in events if event.get("status") == "success")
        failure_count = sum(1 for event in events if event.get("status") == "failure")
        skipped_count = sum(1 for event in events if event.get("status") == "skipped")
        transactions_on_chain = sum(1 for event in events if event.get("tx_id"))
        ipfs_operations = sum(1 for event in events if event.get("ipfs_cid"))

        session_duration_ms = 0
        if events:
            started_at = self._parse_timestamp(str(events[0]["timestamp_iso"]))
            ended_at = self._parse_timestamp(str(events[-1]["timestamp_iso"]))
            session_duration_ms = int((ended_at - started_at).total_seconds() * 1000)

        return {
            "session_id": session_id,
            "total_events": total_events,
            "success_count": success_count,
            "failure_count": failure_count,
            "skipped_count": skipped_count,
            "session_duration_ms": session_duration_ms,
            "transactions_on_chain": transactions_on_chain,
            "ipfs_operations": ipfs_operations,
        }


tracer = FlowTracer(db_path="mercator.db", traces_dir="logs/traces")


def start_session(session_id: Optional[str] = None) -> str:
    if session_id:
        _session_id_var.set(session_id)
        _session_start_time_var.set(time.monotonic())
        tracer.record(
            "session.started",
            "success",
            plain_english_description="New buyer_purchase session started",
            metadata={"session_type": "buyer_purchase"},
        )
        return session_id

    return tracer.start_session()


def get_session_id() -> Optional[str]:
    return tracer.get_current_session_id()


def record_event(
    event_type: str,
    plain_english_description: str,
    metadata: Optional[dict[str, object]] = None,
    *,
    autonomous: bool = False,
) -> None:
    alias_map = {
        "autonomous_approval_check": "agent.auto_approval_check",
    }
    canonical_event_type = alias_map.get(event_type, event_type)

    if autonomous and not plain_english_description.startswith("[AUTO-APPROVED]"):
        plain_english_description = f"[AUTO-APPROVED] {plain_english_description}"

    tracer.record(
        canonical_event_type,
        "success",
        plain_english_description=plain_english_description,
        metadata=metadata,
    )


def export_json(session_id: str) -> str:
    return str(tracer.export_json(session_id))