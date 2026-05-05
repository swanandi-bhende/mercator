from __future__ import annotations

import importlib
import json
import os
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("ALGOD_URL", "https://example.invalid")
os.environ.setdefault("INDEXER_URL", "https://example.invalid")
os.environ.setdefault("INSIGHT_LISTING_APP_ID", "1")
os.environ.setdefault("ESCROW_APP_ID", "1")
os.environ.setdefault("REPUTATION_APP_ID", "1")
os.environ.setdefault("DEPLOYER_ADDRESS", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM")
os.environ.setdefault("BUYER_WALLET", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM")

agent_module = importlib.import_module("backend.agent")
x402_module = importlib.import_module("backend.tools.x402_payment")


def _listing_result(relevance: int, reputation: int, price_usdc: float, listing_id: int = 7) -> str:
    return json.dumps(
        {
            "matches": [
                {
                    "listing_id": listing_id,
                    "relevance_score": relevance,
                    "reputation": reputation,
                    "price_usdc": price_usdc,
                    "price_micro_usdc": int(price_usdc * 1_000_000),
                }
            ]
        }
    )


async def _run_in_thread(func, payload):
    result = func(payload)
    if asyncio.iscoroutine(result):
        return await result
    return result


@pytest.mark.asyncio
async def test_all_thresholds_met_triggers_payment(monkeypatch):
    broadcast_mock = AsyncMock(return_value="TXID-1")

    async def _fake_trigger(payload):
        await broadcast_mock(payload)
        return json.dumps({"success": True, "decision": "BUY", "payment_status": {"payment_details": {"amount_usdc": 0.2}}})

    trigger_mock = AsyncMock(side_effect=_fake_trigger)

    monkeypatch.setattr(agent_module, "semantic_search_tool", SimpleNamespace(ainvoke=AsyncMock(return_value=_listing_result(90, 80, 0.2))))
    monkeypatch.setattr(agent_module, "evaluate_insights", AsyncMock(return_value={"decision": "BUY", "evaluation": "BUY"}))
    monkeypatch.setattr(agent_module, "trigger_x402_payment", SimpleNamespace(ainvoke=trigger_mock))
    monkeypatch.setattr(agent_module, "record_event", MagicMock())
    monkeypatch.setattr(agent_module.asyncio, "to_thread", _run_in_thread)
    monkeypatch.setattr(agent_module.asyncio, "sleep", AsyncMock())

    result = await agent_module.run_agent("test", autonomous_mode=True, dry_run=False)

    assert result["success"] is True
    trigger_mock.assert_awaited_once()
    called_payload = trigger_mock.await_args.args[0]
    assert called_payload["autonomous_mode"] is True
    assert called_payload["relevance_score"] == 90
    assert called_payload["reputation_score"] == 80
    assert called_payload["price_usdc"] == 0.2
    broadcast_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_relevance_below_threshold_skips(monkeypatch):
    trigger_mock = AsyncMock()
    monkeypatch.setattr(agent_module, "semantic_search_tool", SimpleNamespace(ainvoke=AsyncMock(return_value=_listing_result(70, 80, 0.2))))
    monkeypatch.setattr(agent_module, "evaluate_insights", AsyncMock(return_value={"decision": "BUY", "evaluation": "BUY"}))
    monkeypatch.setattr(agent_module, "trigger_x402_payment", SimpleNamespace(ainvoke=trigger_mock))
    monkeypatch.setattr(agent_module.asyncio, "to_thread", _run_in_thread)

    result = await agent_module.run_agent("test", autonomous_mode=True, dry_run=False)

    assert result["decision"] == "SKIP"
    assert "Relevance" in result["skip_reason"]
    assert trigger_mock.await_count == 0


@pytest.mark.asyncio
async def test_reputation_below_threshold_skips(monkeypatch):
    trigger_mock = AsyncMock()
    monkeypatch.setattr(agent_module, "semantic_search_tool", SimpleNamespace(ainvoke=AsyncMock(return_value=_listing_result(90, 60, 0.2))))
    monkeypatch.setattr(agent_module, "evaluate_insights", AsyncMock(return_value={"decision": "BUY", "evaluation": "BUY"}))
    monkeypatch.setattr(agent_module, "trigger_x402_payment", SimpleNamespace(ainvoke=trigger_mock))
    monkeypatch.setattr(agent_module.asyncio, "to_thread", _run_in_thread)

    result = await agent_module.run_agent("test", autonomous_mode=True, dry_run=False)

    assert result["decision"] == "SKIP"
    assert "Reputation" in result["skip_reason"]
    assert trigger_mock.await_count == 0


@pytest.mark.asyncio
async def test_price_above_threshold_skips(monkeypatch):
    trigger_mock = AsyncMock()
    monkeypatch.setattr(agent_module, "semantic_search_tool", SimpleNamespace(ainvoke=AsyncMock(return_value=_listing_result(90, 80, 0.50))))
    monkeypatch.setattr(agent_module, "evaluate_insights", AsyncMock(return_value={"decision": "BUY", "evaluation": "BUY"}))
    monkeypatch.setattr(agent_module, "trigger_x402_payment", SimpleNamespace(ainvoke=trigger_mock))
    monkeypatch.setattr(agent_module.asyncio, "to_thread", _run_in_thread)

    result = await agent_module.run_agent("test", autonomous_mode=True, dry_run=False)

    assert result["decision"] == "SKIP"
    assert "Price" in result["skip_reason"]
    assert trigger_mock.await_count == 0


@pytest.mark.asyncio
async def test_simulation_failure_aborts_autonomous_payment(monkeypatch):
    listing = SimpleNamespace(seller=os.environ["DEPLOYER_ADDRESS"], price=200_000, ipfs_hash="QmCID")
    listing_client = SimpleNamespace(
        state=SimpleNamespace(box=SimpleNamespace(listings=SimpleNamespace(get_value=MagicMock(return_value=listing))))
    )

    class FakeReputationClient:
        def __init__(self):
            self.state = SimpleNamespace(
                box=SimpleNamespace(seller_scores=SimpleNamespace(get_value=MagicMock(return_value=80)))
            )

    class FakeX402Client:
        instances: list["FakeX402Client"] = []

        def __init__(self, _algorand, usdc_asset_id=None, decimals=None):
            self.simulate_payment = AsyncMock(side_effect=RuntimeError("simulation failed"))
            self.send_micropayment = AsyncMock(return_value="NEVER")
            self.send_atomic_payment_and_redeem = AsyncMock(return_value=("PAY", "REDEEM"))
            self.ensure_asset_opt_in = MagicMock(return_value=None)
            FakeX402Client.instances.append(self)

    monkeypatch.setattr(x402_module, "get_insight_listing_client", lambda: listing_client)
    monkeypatch.setattr(x402_module, "get_algorand_client", lambda: MagicMock())
    monkeypatch.setattr(x402_module, "get_reputation_client", lambda: FakeReputationClient())
    monkeypatch.setattr(x402_module, "X402Client", FakeX402Client)

    response = await x402_module.trigger_x402_payment.ainvoke(
        {
            "listing_id": 7,
            "buyer_address": os.environ["DEPLOYER_ADDRESS"],
            "amount_usdc": 0.2,
            "user_approval_input": "approve",
            "autonomous_mode": True,
            "relevance_score": 90,
            "reputation_score": 80,
            "price_usdc": 0.2,
        }
    )
    payload = json.loads(response)

    assert payload["success"] is False
    assert payload["error"] == "SIMULATION_ERROR" or payload["error"] == "AUTO_ABORTED"
    assert payload["message"]
    assert FakeX402Client.instances
    assert FakeX402Client.instances[0].send_micropayment.await_count == 0


@pytest.mark.asyncio
async def test_multi_round_loop_completes_all_rounds(monkeypatch):
    run_agent_mock = AsyncMock(
        side_effect=[
            {"success": True, "decision": "BUY", "payment_status": {"payment_details": {"amount_usdc": 0.1}}},
            {"success": True, "decision": "BUY", "payment_status": {"payment_details": {"amount_usdc": 0.1}}},
            {"success": True, "decision": "BUY", "payment_status": {"payment_details": {"amount_usdc": 0.1}}},
        ]
    )
    monkeypatch.setattr(agent_module, "run_agent", run_agent_mock)
    monkeypatch.setattr(agent_module.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(agent_module, "export_json", MagicMock(return_value="logs/flow_trace_test.json"))
    monkeypatch.setattr(agent_module, "start_session", MagicMock(return_value="session-test"))

    result = await agent_module.run_autonomous_loop(query="test", rounds=3, dry_run=True)

    assert result.rounds_completed == 3
    assert result.purchases_made == 3
    assert result.session_id == "session-test"
    assert run_agent_mock.await_count == 3
