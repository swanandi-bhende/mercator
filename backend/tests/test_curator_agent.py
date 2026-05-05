"""Tests for the curator agent runtime and scheduler-facing helpers."""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture()
def curator_module(monkeypatch, tmp_path):
    monkeypatch.setenv("CURATOR_DB_PATH", str(tmp_path / "mercator.db"))
    monkeypatch.setenv("CURATOR_WALLET_ADDRESS", "Z2CMWJRIQH4IEVCMEPLWEIDH56K7KP6V5NASO2LVU4GTCII7VM7NNHYCQA")
    monkeypatch.setenv("CURATOR_MIN_DATA_QUALITY_SCORE", "0.7")
    monkeypatch.setenv("CURATOR_DEFAULT_SYMBOLS", "RELIANCE.NS,TCS.NS")
    monkeypatch.setenv("CURATOR_LISTING_URL", "http://testserver/list")
    module = importlib.import_module("backend.agents.curator_agent")
    importlib.reload(module)
    return module


@pytest.fixture()
def db_module(monkeypatch, tmp_path):
    monkeypatch.setenv("CURATOR_DB_PATH", str(tmp_path / "mercator.db"))
    module = importlib.import_module("backend.utils.db")
    importlib.reload(module)
    return module


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object] | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or ""

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_high_quality_cycle_publishes(curator_module, monkeypatch, db_module):
    snapshot = SimpleNamespace(
        symbol="RELIANCE.NS",
        provider_symbol="RELIANCE.NS",
        data_quality_score=0.8,
        current_price=100.0,
        previous_close=95.0,
        volume=1_000,
        average_volume=800,
    )
    insight = SimpleNamespace(
        headline="Strong quarter",
        summary="Revenue improved",
        thesis="Demand remains strong",
        direction="bullish",
        quality_score=0.8,
        confidence=0.75,
        price_usdc=1.25,
        evidence=["headline 1"],
    )

    monkeypatch.setattr(curator_module, "fetch_market_snapshot", MagicMock(return_value=snapshot))
    monkeypatch.setattr(curator_module, "synthesise_insight", MagicMock(return_value=insight))
    monkeypatch.setattr(curator_module, "_publish_listing", AsyncMock(return_value=("TXID-123", "CID-123")))
    result = await curator_module.run_cycle_for_symbol("RELIANCE.NS")

    assert result.published is True
    assert result.listing_tx_id == "TXID-123"
    assert result.skip_reason == ""
    assert result.error == ""
    rows = db_module.fetch_curator_recent_runs(1)
    assert rows[0]["symbol"] == "RELIANCE.NS"
    assert rows[0]["published"] == 1


@pytest.mark.asyncio
async def test_low_quality_snapshot_skips(curator_module, monkeypatch):
    snapshot = SimpleNamespace(
        symbol="RELIANCE.NS",
        provider_symbol="RELIANCE.NS",
        data_quality_score=0.4,
        current_price=None,
        previous_close=None,
        volume=None,
        average_volume=None,
    )
    monkeypatch.setattr(curator_module, "fetch_market_snapshot", MagicMock(return_value=snapshot))
    result = await curator_module.run_cycle_for_symbol("RELIANCE.NS")

    assert result.published is False
    assert "quality" in result.skip_reason.lower()


@pytest.mark.asyncio
async def test_low_confidence_synthesis_skips(curator_module, monkeypatch):
    snapshot = SimpleNamespace(
        symbol="TCS.NS",
        provider_symbol="TCS.NS",
        data_quality_score=0.9,
        current_price=100.0,
        previous_close=99.0,
        volume=1_000,
        average_volume=900,
    )
    insight = SimpleNamespace(
        headline="Headline",
        summary="Summary",
        thesis="Thesis",
        direction="neutral",
        quality_score=0.8,
        confidence=0.4,
        price_usdc=1.0,
        evidence=["headline 1"],
    )
    monkeypatch.setattr(curator_module, "fetch_market_snapshot", MagicMock(return_value=snapshot))
    monkeypatch.setattr(curator_module, "synthesise_insight", MagicMock(return_value=insight))

    result = await curator_module.run_cycle_for_symbol("TCS.NS")

    assert result.published is False
    assert "confidence" in result.skip_reason.lower()


@pytest.mark.asyncio
async def test_gemini_parse_failure_retries_once(monkeypatch):
    module = importlib.import_module("backend.agents.insight_synthesiser")
    importlib.reload(module)

    snapshot = SimpleNamespace(
        symbol="INFY.NS",
        provider_symbol="INFY.NS",
        fetched_at=datetime.now(timezone.utc),
        current_price=100.0,
        previous_close=98.0,
        open_price=99.0,
        day_high=101.0,
        day_low=97.0,
        volume=1_000,
        market_cap=10_000,
        currency="INR",
        trailing_pe=20.0,
        notes=[],
        as_dict=lambda: {
            "symbol": "INFY.NS",
            "provider_symbol": "INFY.NS",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "current_price": 100.0,
            "previous_close": 98.0,
            "open_price": 99.0,
            "day_high": 101.0,
            "day_low": 97.0,
            "volume": 1_000,
            "market_cap": 10_000,
            "currency": "INR",
            "trailing_pe": 20.0,
            "notes": [],
            "data_quality_score": 1.0,
        },
        data_quality_score=1.0,
    )

    class FakeLLM:
        def __init__(self, *args, **kwargs):
            self.calls = 0

        def invoke(self, prompt):
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(content="not json")
            return SimpleNamespace(
                content=(
                    '{"headline":"H","summary":"S","thesis":"T","direction":"bullish",'
                    '"quality_score":0.9,"confidence":0.8,"risk_note":"R",'
                    '"evidence":["e1"],"tags":["t1"]}'
                )
            )

    monkeypatch.setattr(module, "ChatGoogleGenerativeAI", FakeLLM)
    monkeypatch.setattr(module, "_fetch_headlines", lambda *args, **kwargs: ["headline"])
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    insight = module.synthesise_insight(snapshot)
    assert insight.headline == "H"


@pytest.mark.asyncio
async def test_listing_endpoint_failure_records_error(curator_module, monkeypatch, db_module):
    snapshot = SimpleNamespace(
        symbol="RELIANCE.NS",
        provider_symbol="RELIANCE.NS",
        data_quality_score=0.9,
        current_price=100.0,
        previous_close=95.0,
        volume=1_000,
        average_volume=800,
    )
    insight = SimpleNamespace(
        headline="Headline",
        summary="Summary",
        thesis="Thesis",
        direction="bullish",
        quality_score=0.8,
        confidence=0.9,
        price_usdc=1.25,
        evidence=["e1"],
    )
    monkeypatch.setattr(curator_module, "fetch_market_snapshot", MagicMock(return_value=snapshot))
    monkeypatch.setattr(curator_module, "synthesise_insight", MagicMock(return_value=insight))
    monkeypatch.setattr(curator_module, "_publish_listing", AsyncMock(side_effect=RuntimeError("HTTP 500: boom")))

    result = await curator_module.run_cycle_for_symbol("RELIANCE.NS")

    assert result.published is False
    assert "boom" in result.error
    rows = db_module.fetch_curator_recent_runs(1)
    assert rows[0]["published"] == 0


@pytest.mark.asyncio
async def test_full_cycle_processes_all_symbols(curator_module, monkeypatch):
    symbols = ["RELIANCE.NS", "TCS.NS"]
    monkeypatch.setenv("CURATOR_DEFAULT_SYMBOLS", ",".join(symbols))
    monkeypatch.setattr(curator_module, "run_cycle_for_symbol", AsyncMock(side_effect=[
        curator_module.CuratorRunResult(run_id="1", symbol="RELIANCE.NS"),
        curator_module.CuratorRunResult(run_id="2", symbol="TCS.NS"),
    ]))
    monkeypatch.setattr(curator_module.asyncio, "sleep", AsyncMock())

    results = await curator_module.run_full_cycle()

    assert [result.symbol for result in results] == symbols


@pytest.mark.asyncio
async def test_status_and_admin_trigger_endpoints(monkeypatch, tmp_path):
    monkeypatch.setenv("CURATOR_DB_PATH", str(tmp_path / "mercator.db"))
    monkeypatch.setenv("CURATOR_DEFAULT_SYMBOLS", "RELIANCE.NS,TCS.NS")
    monkeypatch.setenv("ADMIN_KEY", "secret")
    monkeypatch.setattr("backend.agents.curator_agent.run_full_cycle", AsyncMock(return_value=[]))

    main_module = importlib.import_module("backend.main")
    importlib.reload(main_module)
    main_module.scheduler.remove_all_jobs()
    main_module.scheduler.add_job(lambda: None, "interval", minutes=30, id="curator_cycle", replace_existing=True)

    client = TestClient(main_module.app)
    status = client.get("/curator/status")
    assert status.status_code == 200
    assert "scheduler_running" in status.json()

    trigger = client.post("/admin/curator/trigger_now", headers={"X-Admin-Key": "secret"})
    assert trigger.status_code == 200
    assert trigger.json() == []
