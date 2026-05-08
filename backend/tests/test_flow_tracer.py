from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import main as main_module
from backend.utils.flow_tracer import FlowTracer, _session_id_var


UUID4_REGEX = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def _make_tracer(tmp_path: Path) -> FlowTracer:
    return FlowTracer(
        db_path=str(tmp_path / "flow_events.db"),
        traces_dir=str(tmp_path / "traces"),
    )


def _row_count(db_path: Path) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM flow_events").fetchone()
        return int(row[0] if row else 0)


@pytest.mark.asyncio
async def test_start_session_sets_context_var(tmp_path: Path):
    tracer = _make_tracer(tmp_path)
    session_id = tracer.start_session()

    assert UUID4_REGEX.match(session_id)
    assert tracer.get_current_session_id() == session_id


def test_record_outside_session_discards_event(tmp_path: Path):
    tracer = _make_tracer(tmp_path)
    _session_id_var.set(None)

    event = tracer.record(
        "ipfs.upload_started",
        "pending",
        plain_english_description="test",
    )

    assert event is None
    assert _row_count(tmp_path / "flow_events.db") == 0


def test_record_unknown_event_name_logs_warning(tmp_path: Path):
    tracer = _make_tracer(tmp_path)
    tracer.start_session("buyer_purchase")

    event = tracer.record(
        "unknown.event",
        "success",
        plain_english_description="test",
    )

    assert event is not None
    with sqlite3.connect(tmp_path / "flow_events.db") as conn:
        row = conn.execute(
            "SELECT event_name FROM flow_events WHERE event_id = ?",
            (event.event_id,),
        ).fetchone()

    assert row is not None
    assert row[0] == "unknown.event"


@pytest.mark.asyncio
async def test_pending_resolution_calculates_duration(tmp_path: Path):
    tracer = _make_tracer(tmp_path)
    tracer.start_session("buyer_purchase")

    event_id = tracer.start_event(
        "payment.simulation_started",
        plain_english_description="Payment simulation started",
    )
    await asyncio.sleep(0.05)
    resolved_event = tracer.resolve_event(
        event_id,
        "success",
        plain_english_description="Payment simulation completed",
    )

    assert resolved_event is not None
    assert resolved_event.duration_ms is not None
    assert resolved_event.duration_ms >= 50


@pytest.mark.asyncio
async def test_concurrent_sessions_do_not_interfere(tmp_path: Path):
    tracer = _make_tracer(tmp_path)

    async def worker(tag: str) -> str:
        session_id = tracer.start_session(f"session_{tag}")
        for index in range(5):
            tracer.record(
                "agent.search_started",
                "success",
                plain_english_description=f"worker={tag} event={index}",
            )
            await asyncio.sleep(0)
        return session_id

    session_a, session_b = await asyncio.gather(worker("a"), worker("b"))

    with sqlite3.connect(tmp_path / "flow_events.db") as conn:
        rows = conn.execute(
            """
            SELECT session_id, COUNT(*)
            FROM flow_events
            WHERE event_name != 'session.started'
            GROUP BY session_id
            """
        ).fetchall()

    counts = {row[0]: int(row[1]) for row in rows}
    assert len(counts) == 2
    assert counts[session_a] == 5
    assert counts[session_b] == 5
    assert sum(counts.values()) == 10


def test_export_json_contains_all_events(tmp_path: Path):
    tracer = _make_tracer(tmp_path)
    session_id = tracer.start_session("buyer_purchase")

    for index in range(12):
        tracer.record(
            "agent.search_started",
            "success",
            plain_english_description=f"event {index}",
        )

    export_path = tracer.export_json(session_id)
    payload = json.loads(export_path.read_text(encoding="utf-8"))

    assert payload["session_id"] == session_id
    assert payload["total_events"] == 13


def test_export_csv_contains_headers(tmp_path: Path):
    tracer = _make_tracer(tmp_path)
    session_id = tracer.start_session("buyer_purchase")
    tracer.record(
        "agent.search_started",
        "success",
        plain_english_description="csv event",
    )

    csv_path = tracer.export_csv(session_id)
    header = csv_path.read_text(encoding="utf-8").splitlines()[0]

    for field in [
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
    ]:
        assert field in header


def test_download_endpoint_returns_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    local_tracer = _make_tracer(tmp_path)
    session_id = local_tracer.start_session("buyer_purchase")
    local_tracer.record(
        "agent.search_started",
        "success",
        plain_english_description="download event",
    )

    monkeypatch.setattr(main_module, "tracer", local_tracer)

    with TestClient(main_module.app) as client:
        response = client.get(f"/traces/{session_id}/download")

    assert response.status_code == 200
    content_disposition = response.headers.get("content-disposition", "")
    assert "attachment" in content_disposition
    assert f"flow_trace_{session_id}.json" in content_disposition

    parsed = response.json()
    assert parsed["session_id"] == session_id
    assert parsed["total_events"] >= 2
