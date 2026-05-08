from __future__ import annotations

import asyncio
import os
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from backend import main as main_module
from backend.tools import x402_payment as x402_module
from backend.utils.ws_manager import ws_manager


@pytest.fixture(autouse=True)
def reset_ws_manager_state() -> None:
    ws_manager.active_connections.clear()
    ws_manager.recent_events.clear()


@pytest.mark.asyncio
async def test_client_connects_and_receives_ping(monkeypatch):
    freeze_ctx = nullcontext()
    try:
        from freezegun import freeze_time

        freeze_ctx = freeze_time("2026-05-08 12:00:00")
    except Exception:
        freeze_ctx = nullcontext()

    with freeze_ctx:
        with TestClient(main_module.app) as client:
            with client.websocket_connect("/ws?token=demo") as websocket:
                await main_module._send_heartbeat()
                message = websocket.receive_json()

    assert message["event_type"] == "ping"
    assert "timestamp" in message


@pytest.mark.asyncio
async def test_broadcast_reaches_all_connected_clients():
    with TestClient(main_module.app) as client:
        with client.websocket_connect("/ws?token=a") as ws1, client.websocket_connect("/ws?token=b") as ws2, client.websocket_connect("/ws?token=c") as ws3:
            await ws_manager.broadcast("test_event", {"key": "value"})

            msg1 = ws1.receive_json()
            msg2 = ws2.receive_json()
            msg3 = ws3.receive_json()

    for message in (msg1, msg2, msg3):
        assert message["event_type"] == "test_event"
        assert "timestamp" in message
        assert message["payload"] == {"key": "value"}


@pytest.mark.asyncio
async def test_disconnected_client_is_removed_from_active_set():
    with TestClient(main_module.app) as client:
        with client.websocket_connect("/ws?token=z") as websocket:
            assert ws_manager.get_connection_count() == 1
            websocket.close(code=1000)
            await ws_manager.broadcast("test_event", {"ok": True})
            assert ws_manager.get_connection_count() == 0


@pytest.mark.asyncio
async def test_new_listing_broadcast_triggered_by_post_list(monkeypatch):
    seller_wallet = os.getenv(
        "DEPLOYER_ADDRESS",
        "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM",
    )

    broadcast_mock = AsyncMock()
    monkeypatch.setattr(main_module.ws_manager, "broadcast", broadcast_mock)
    monkeypatch.setattr(main_module, "_resolve_signer_for_wallet", lambda _wallet: ("mnemonic", seller_wallet, True))
    monkeypatch.setattr(main_module, "upload_insight_to_ipfs", AsyncMock(return_value="CID123"))
    monkeypatch.setattr(main_module, "store_cid_in_listing", lambda **_kwargs: (101, 202))
    monkeypatch.setattr(main_module, "_poll_for_listing_confirmation", AsyncMock(return_value="TX123"))
    monkeypatch.setattr(main_module, "_ensure_listing_app_funded", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main_module, "clear_semantic_search_cache", lambda: None)
    monkeypatch.setattr(main_module, "_fetch_fee_config_state", lambda: {"fee_rate_bps": 250})

    request = main_module.ListingRequest(
        insight_text="This is a realtime listing update for websocket integration tests.",
        price=1.25,
        seller_wallet=seller_wallet,
        source_type="curator_agent",
    )

    response = await main_module.create_listing(request)

    assert response["success"] is True
    assert broadcast_mock.await_count == 1
    event_type, payload = broadcast_mock.await_args.args
    assert event_type == "new_listing"
    assert payload["listing_id"] == "101"


@pytest.mark.asyncio
async def test_autonomous_decision_broadcast(monkeypatch):
    buyer_wallet = os.getenv(
        "BUYER_WALLET",
        "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM",
    )
    seller_wallet = os.getenv(
        "SELLER_ADDRESS",
        "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM",
    )

    broadcast_mock = AsyncMock()
    monkeypatch.setattr(x402_module.ws_manager, "broadcast", broadcast_mock)
    monkeypatch.setattr(x402_module, "record_event", MagicMock())
    monkeypatch.setattr(x402_module, "get_algorand_client", lambda: SimpleNamespace(client=SimpleNamespace(algod=None)))

    listing_obj = SimpleNamespace(seller=seller_wallet, price=1_000_000)
    listing_client = SimpleNamespace(
        state=SimpleNamespace(
            box=SimpleNamespace(
                listings=SimpleNamespace(get_value=lambda _listing_id: listing_obj),
            )
        )
    )
    monkeypatch.setattr(x402_module, "get_insight_listing_client", lambda: listing_client)

    reputation_client = SimpleNamespace(
        state=SimpleNamespace(
            box=SimpleNamespace(
                seller_scores=SimpleNamespace(get_value=lambda _seller: 65),
            )
        )
    )
    monkeypatch.setattr(x402_module, "get_reputation_client", lambda: reputation_client)
    monkeypatch.setattr(
        x402_module,
        "check_auto_conditions",
        lambda **_kwargs: SimpleNamespace(
            approved=False,
            rejection_reason="relevance below threshold",
            thresholds_used={
                "AUTO_MIN_RELEVANCE": 80,
                "AUTO_MIN_REPUTATION": 70,
                "AUTO_MAX_PRICE_USDC": 3.0,
            },
        ),
    )

    await x402_module.trigger_x402_payment.ainvoke(
        {
            "listing_id": 77,
            "buyer_address": buyer_wallet,
            "amount_usdc": 1.0,
            "autonomous_mode": True,
            "relevance_score": 50,
            "price_usdc": 1.0,
        }
    )

    assert broadcast_mock.await_count >= 1
    event_type, payload = broadcast_mock.await_args.args
    assert event_type == "autonomous_decision"
    assert payload["decision"] == "SKIP"
    assert payload["rejection_reason"] == "relevance below threshold"
