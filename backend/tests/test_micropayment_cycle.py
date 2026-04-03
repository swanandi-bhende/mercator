from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_ENV_FILE = REPO_ROOT / ".env.testnet"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))



def _set_env_if_present(key: str, value: str | None) -> None:
    if value is None:
        return
    if str(value).strip():
        os.environ[key] = str(value).strip()


# Prime environment before importing backend modules that validate env at import time.
for env_key, env_value in dotenv_values(TEST_ENV_FILE).items():
    _set_env_if_present(env_key, env_value)

_set_env_if_present("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY") or "test-gemini-key")
_set_env_if_present("PINATA_JWT", os.getenv("PINATA_JWT") or "test-pinata-jwt")
_set_env_if_present("ALGOD_URL", os.getenv("ALGOD_URL") or "https://testnet-api.algonode.cloud")
_set_env_if_present("INDEXER_URL", os.getenv("INDEXER_URL") or "https://testnet-idx.algonode.cloud")
_set_env_if_present("ALGOD_SERVER", os.getenv("ALGOD_SERVER") or os.getenv("ALGOD_URL"))
_set_env_if_present("INDEXER_SERVER", os.getenv("INDEXER_SERVER") or os.getenv("INDEXER_URL"))
_set_env_if_present("USDC_ASA_ID", os.getenv("USDC_ASA_ID") or "10458941")

from backend import main as backend_main

semantic_module = importlib.import_module("backend.tools.semantic_search")


@pytest.fixture()
def mock_env(monkeypatch):
    values = dotenv_values(TEST_ENV_FILE)
    for key, value in values.items():
        if value is None:
            continue
        if not str(value).strip():
            continue
        monkeypatch.setenv(key, str(value).strip())

    monkeypatch.setenv("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", "test-gemini-key"))
    monkeypatch.setenv("PINATA_JWT", os.getenv("PINATA_JWT", "test-pinata-jwt"))
    monkeypatch.setenv("ALGOD_URL", os.getenv("ALGOD_URL", "https://testnet-api.algonode.cloud"))
    monkeypatch.setenv("INDEXER_URL", os.getenv("INDEXER_URL", "https://testnet-idx.algonode.cloud"))
    monkeypatch.setenv("ALGOD_SERVER", os.getenv("ALGOD_SERVER", os.getenv("ALGOD_URL", "https://testnet-api.algonode.cloud")))
    monkeypatch.setenv("INDEXER_SERVER", os.getenv("INDEXER_SERVER", os.getenv("INDEXER_URL", "https://testnet-idx.algonode.cloud")))
    monkeypatch.setenv("USDC_ASA_ID", os.getenv("USDC_ASA_ID", "10458941"))
    return values


@pytest.fixture()
def mock_algod_client():
    client = MagicMock(name="mock_algod_client")
    client.account_info.return_value = {"amount": 10_000_000, "min-balance": 100_000, "assets": []}
    client.suggested_params.return_value = SimpleNamespace(flat_fee=False)
    client.send_transaction.return_value = "MOCK_TXID"
    client.wait_for_confirmation.return_value = {"confirmed-round": 123}
    return client


@pytest.fixture()
def mock_indexer():
    indexer_client = MagicMock(name="mock_indexer")
    indexer_client.search_transactions.return_value = {"transactions": []}
    indexer_client.transaction.return_value = {"transaction": {"confirmed-round": 123}}
    indexer_client.account_info.return_value = {"account": {"assets": []}}
    return indexer_client


@pytest.fixture()
def mock_ipfs_upload():
    return AsyncMock(return_value="QmMockCID")


@pytest.fixture()
def mock_ipfs_fetch():
    return AsyncMock(return_value="Sample trading insight: Buy NIFTY above 24500 with SL 24380")


@pytest.fixture()
def mock_x402_client():
    client = SimpleNamespace()
    client.simulate_payment = AsyncMock(
        return_value={
            "success": True,
            "sender": "BUYER",
            "receiver": "SELLER",
            "amount": 1_000_000,
            "asset_id": int(os.getenv("USDC_ASA_ID", "10458941")),
            "estimated_fee": False,
            "is_safe": True,
        }
    )
    client.send_micropayment = AsyncMock(return_value="MOCK_PAYMENT_TX")
    client.ensure_asset_opt_in = MagicMock(return_value=None)
    return client


@pytest.fixture()
def mock_gemini_llm():
    llm = MagicMock(name="mock_gemini_llm")
    llm.invoke.return_value = SimpleNamespace(
        content="Reasoning:\n1. Relevance: 90\n2. Reputation check: 80\n3. Value-for-price: 90\n4. Final rationale: BUY\nDecision: BUY"
    )
    return llm


@pytest.fixture()
def mock_insight_listing_client():
    return SimpleNamespace(
        state=SimpleNamespace(
            box=SimpleNamespace(
                listings=SimpleNamespace(get_map=MagicMock(return_value={}))
            )
        )
    )


@pytest.fixture()
def mock_reputation_client():
    return SimpleNamespace(
        state=SimpleNamespace(
            box=SimpleNamespace(
                seller_scores=SimpleNamespace(get_value=MagicMock(return_value=0))
            )
        )
    )


@pytest.fixture()
def client(
    mock_env,
    mock_algod_client,
    monkeypatch,
):
    monkeypatch.setattr(backend_main, "_get_algod_client", lambda: mock_algod_client)
    monkeypatch.setattr(backend_main, "_get_indexer_client", lambda: MagicMock())
    return TestClient(backend_main.app)


@pytest.fixture()
def list_call_mocks(mock_env, mock_algod_client, monkeypatch):
    upload_mock = AsyncMock(return_value="QmMockCID")
    store_mock = MagicMock(return_value=(4, 758196266))
    poll_mock = AsyncMock(return_value="MOCK_LISTING_TX")
    monkeypatch.setattr(backend_main, "_get_algod_client", lambda: mock_algod_client)
    monkeypatch.setattr(backend_main, "upload_insight_to_ipfs", upload_mock)
    monkeypatch.setattr(backend_main, "store_cid_in_listing", store_mock)
    monkeypatch.setattr(backend_main, "_poll_for_listing_confirmation", poll_mock)
    return upload_mock, store_mock, poll_mock


LISTING_CASES = [
    pytest.param(
        {
            "name": "valid_upload_one",
            "payload": {
                "insight_text": "Sample trading insight: Buy NIFTY above 24500 with SL 24380",
                "price": "1.00",
                "seller_wallet": os.getenv("DEPLOYER_ADDRESS", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM"),
            },
            "cid": "QmValidCID1",
            "listing_id": 4,
            "asa_id": 758196266,
            "status": 200,
        },
        id="valid_upload_one",
    ),
    pytest.param(
        {
            "name": "valid_upload_two",
            "payload": {
                "insight_text": "Sample trading insight: Sell NIFTY below 24500 on weakness",
                "price": "2.50",
                "seller_wallet": os.getenv("DEPLOYER_ADDRESS", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM"),
            },
            "cid": "QmValidCID2",
            "listing_id": 8,
            "asa_id": 758196267,
            "status": 200,
        },
        id="valid_upload_two",
    ),
    pytest.param(
        {
            "name": "negative_price",
            "payload": {
                "insight_text": "Sample trading insight: Buy NIFTY above 24500 with SL 24380",
                "price": "-1.00",
                "seller_wallet": os.getenv("DEPLOYER_ADDRESS", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM"),
            },
            "status": 400,
        },
        id="negative_price",
    ),
    pytest.param(
        {
            "name": "empty_text",
            "payload": {
                "insight_text": "   ",
                "price": "1.00",
                "seller_wallet": os.getenv("DEPLOYER_ADDRESS", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM"),
            },
            "status": 400,
        },
        id="empty_text",
    ),
    pytest.param(
        {
            "name": "bad_wallet",
            "payload": {
                "insight_text": "Sample trading insight: Buy NIFTY above 24500 with SL 24380",
                "price": "1.00",
                "seller_wallet": "BAD_WALLET",
            },
            "status": 400,
        },
        id="bad_wallet",
    ),
    pytest.param(
        {
            "name": "ipfs_upload_failure",
            "payload": {
                "insight_text": "Sample trading insight: Buy NIFTY above 24500 with SL 24380",
                "price": "1.00",
                "seller_wallet": os.getenv("DEPLOYER_ADDRESS", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM"),
            },
            "upload_side_effect": backend_main.IPFSUploadError("IPFS failed"),
            "status": 500,
        },
        id="ipfs_upload_failure",
    ),
    pytest.param(
        {
            "name": "onchain_store_failure",
            "payload": {
                "insight_text": "Sample trading insight: Buy NIFTY above 24500 with SL 24380",
                "price": "1.00",
                "seller_wallet": os.getenv("DEPLOYER_ADDRESS", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM"),
            },
            "store_side_effect": backend_main.ListingStoreError("store failed"),
            "status": 500,
        },
        id="onchain_store_failure",
    ),
    pytest.param(
        {
            "name": "confirmation_timeout",
            "payload": {
                "insight_text": "Sample trading insight: Buy NIFTY above 24500 with SL 24380",
                "price": "1.00",
                "seller_wallet": os.getenv("DEPLOYER_ADDRESS", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM"),
            },
            "poll_side_effect": RuntimeError("timed out"),
            "status": 500,
        },
        id="confirmation_timeout",
    ),
]


@pytest.mark.parametrize("case", LISTING_CASES)
def test_list_endpoint_matrix(client, list_call_mocks, case):
    upload_mock, store_mock, poll_mock = list_call_mocks
    payload = case["payload"]

    if "upload_side_effect" in case:
        upload_mock.side_effect = case["upload_side_effect"]
    if "store_side_effect" in case:
        store_mock.side_effect = case["store_side_effect"]
    if "poll_side_effect" in case:
        poll_mock.side_effect = case["poll_side_effect"]

    response = client.post("/list", json=payload)
    assert response.status_code == case["status"]

    if case["status"] == 200:
        body = response.json()
        assert bool(body["success"]) is True
        assert body["listing_id"] == 4
        assert body["asa_id"] == 758196266
        assert body["cid"] == "QmMockCID"
        assert body["txId"] == "MOCK_LISTING_TX"
        assert body["transaction_id"] == "MOCK_LISTING_TX"
        upload_mock.assert_awaited_once_with(payload["insight_text"].strip())
        store_mock.assert_called_once()
        assert store_mock.call_args.kwargs["cid"] == "QmMockCID"
        assert store_mock.call_args.kwargs["price"] == int(float(payload["price"]) * 1_000_000)
        assert store_mock.call_args.kwargs["seller_address"] == payload["seller_wallet"]
        assert poll_mock.await_count == 1
    else:
        if case["name"] == "ipfs_upload_failure":
            assert upload_mock.await_count == 1
            assert store_mock.call_count == 0
            assert poll_mock.await_count == 0
        elif case["name"] == "onchain_store_failure":
            assert upload_mock.await_count == 1
            assert store_mock.call_count == 1
            assert poll_mock.await_count == 0
        elif case["name"] == "confirmation_timeout":
            assert upload_mock.await_count == 1
            assert store_mock.call_count == 1
            assert poll_mock.await_count == 1
        else:
            assert upload_mock.await_count == 0
            assert store_mock.call_count == 0
            assert poll_mock.await_count == 0


BASE_LISTINGS = [
    {
        "listing_id": 1,
        "seller": "seller_a",
        "price": 1_000_000,
        "asa_id": 101,
        "cid": "QmAlpha",
        "text": "alpha listing",
        "vector": np.array([1.0, 0.0], dtype=float),
    },
    {
        "listing_id": 2,
        "seller": "seller_b",
        "price": 1_000_000,
        "asa_id": 102,
        "cid": "QmBeta",
        "text": "beta listing",
        "vector": np.array([0.8, 0.2], dtype=float),
    },
    {
        "listing_id": 3,
        "seller": "seller_c",
        "price": 1_000_000,
        "asa_id": 103,
        "cid": "QmGamma",
        "text": "gamma listing",
        "vector": np.array([0.2, 0.8], dtype=float),
    },
    {
        "listing_id": 4,
        "seller": "seller_d",
        "price": 1_000_000,
        "asa_id": 104,
        "cid": "QmDelta",
        "text": "delta listing",
        "vector": np.array([0.0, 1.0], dtype=float),
    },
]


SEMANTIC_SCENARIOS = [
    {
        "name": "query_alpha_heavy",
        "query": "q_alpha_heavy",
        "query_vector": np.array([1.0, 0.0], dtype=float),
        "reputations": {"seller_a": 90, "seller_b": 60, "seller_c": 40, "seller_d": 10},
    },
    {
        "name": "query_beta_bias",
        "query": "q_beta_bias",
        "query_vector": np.array([0.9, 0.1], dtype=float),
        "reputations": {"seller_a": 20, "seller_b": 85, "seller_c": 50, "seller_d": 10},
    },
    {
        "name": "query_gamma_bias",
        "query": "q_gamma_bias",
        "query_vector": np.array([0.1, 0.9], dtype=float),
        "reputations": {"seller_a": 20, "seller_b": 50, "seller_c": 88, "seller_d": 30},
    },
    {
        "name": "query_delta_bias",
        "query": "q_delta_bias",
        "query_vector": np.array([0.0, 1.0], dtype=float),
        "reputations": {"seller_a": 10, "seller_b": 30, "seller_c": 60, "seller_d": 95},
    },
    {
        "name": "query_midpoint_one",
        "query": "q_midpoint_one",
        "query_vector": np.array([0.6, 0.4], dtype=float),
        "reputations": {"seller_a": 50, "seller_b": 70, "seller_c": 45, "seller_d": 20},
    },
    {
        "name": "query_midpoint_two",
        "query": "q_midpoint_two",
        "query_vector": np.array([0.4, 0.6], dtype=float),
        "reputations": {"seller_a": 30, "seller_b": 40, "seller_c": 75, "seller_d": 80},
    },
    {
        "name": "query_spread_one",
        "query": "q_spread_one",
        "query_vector": np.array([0.75, 0.25], dtype=float),
        "reputations": {"seller_a": 80, "seller_b": 65, "seller_c": 35, "seller_d": 15},
    },
    {
        "name": "query_spread_two",
        "query": "q_spread_two",
        "query_vector": np.array([0.25, 0.75], dtype=float),
        "reputations": {"seller_a": 15, "seller_b": 35, "seller_c": 65, "seller_d": 80},
    },
    {
        "name": "query_diagonal_one",
        "query": "q_diagonal_one",
        "query_vector": np.array([0.7, 0.7], dtype=float),
        "reputations": {"seller_a": 45, "seller_b": 90, "seller_c": 90, "seller_d": 55},
    },
    {
        "name": "query_diagonal_two",
        "query": "q_diagonal_two",
        "query_vector": np.array([0.5, 0.5], dtype=float),
        "reputations": {"seller_a": 55, "seller_b": 50, "seller_c": 85, "seller_d": 75},
    },
]


def _build_listing_map() -> dict[int, SimpleNamespace]:
    listings: dict[int, SimpleNamespace] = {}
    for row in BASE_LISTINGS:
        listings[row["listing_id"]] = SimpleNamespace(
            seller=row["seller"],
            price=row["price"],
            ipfs_hash=row["cid"],
            asa_id=row["asa_id"],
        )
    return listings


def _expected_ranking(query_vector: np.ndarray, reputations: dict[str, int]) -> list[int]:
    def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
        denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
        if denominator == 0.0:
            return 0.0
        return float(np.dot(left, right) / denominator)

    scored: list[tuple[int, float]] = []
    for row in BASE_LISTINGS:
        relevance = cosine_similarity(query_vector, row["vector"])
        reputation_norm = min(max(float(reputations[row["seller"]]), 0.0), 100.0) / 100.0
        score = round(0.7 * relevance + 0.3 * reputation_norm, 6)
        scored.append((row["listing_id"], score))

    return [listing_id for listing_id, _ in sorted(scored, key=lambda item: item[1], reverse=True)[:3]]


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", SEMANTIC_SCENARIOS, ids=[scenario["name"] for scenario in SEMANTIC_SCENARIOS])
async def test_semantic_search_ranking_and_cache(
    monkeypatch,
    mock_env,
    mock_indexer,
    mock_insight_listing_client,
    mock_reputation_client,
    mock_ipfs_fetch,
    scenario,
):
    semantic_module._query_cache.clear()

    listings = _build_listing_map()
    mock_insight_listing_client.state.box.listings.get_map.return_value = listings
    monkeypatch.setattr(semantic_module, "get_insight_listing_client", lambda: mock_insight_listing_client)
    monkeypatch.setattr(semantic_module, "get_reputation_client", lambda: mock_reputation_client)
    monkeypatch.setattr(semantic_module, "get_indexer_client", lambda: mock_indexer)

    cid_to_text = {row["cid"]: row["text"] for row in BASE_LISTINGS}
    mock_ipfs_fetch.side_effect = lambda cid: cid_to_text[cid]
    monkeypatch.setattr(semantic_module, "fetch_insight_from_ipfs", mock_ipfs_fetch)

    vector_map = {scenario["query"]: scenario["query_vector"]}
    vector_map.update({row["text"]: row["vector"] for row in BASE_LISTINGS})

    embed_mock = MagicMock(side_effect=lambda text: np.array(vector_map[text], dtype=float))
    monkeypatch.setattr(semantic_module, "_embed_text", embed_mock)

    reputation_map = scenario["reputations"]
    mock_reputation_client.state.box.seller_scores.get_value.side_effect = lambda seller: reputation_map[seller]

    first_result = await semantic_module.semantic_search.ainvoke({"query": scenario["query"]})
    first_payload = json.loads(first_result)
    expected_ids = _expected_ranking(scenario["query_vector"], reputation_map)

    assert len(first_payload["matches"]) == 3
    assert [entry["listing_id"] for entry in first_payload["matches"]] == expected_ids
    assert first_payload["embedding_fallback"] is False
    assert embed_mock.call_count == 5
    assert mock_ipfs_fetch.await_count == 4

    second_result = await semantic_module.semantic_search.ainvoke({"query": scenario["query"]})
    assert second_result == first_result
    assert embed_mock.call_count == 5
    assert mock_ipfs_fetch.await_count == 4
