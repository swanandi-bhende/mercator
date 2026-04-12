"""End-to-end matrix tests for listing, discovery, payment, and delivery.

Purpose: Verify full Mercator micropayment cycle behavior and edge-case regressions.
"""

from __future__ import annotations

import importlib
import itertools
import json
import os
import re
import sys
import time
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
agent_module = importlib.import_module("backend.agent")
x402_module = importlib.import_module("backend.tools.x402_payment")
post_payment_module = importlib.import_module("backend.tools.post_payment_flow")


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


EVALUATION_OUTPUT_PATTERN = re.compile(
    r"^Reasoning:\n"
    r"1\. Relevance: .+\n"
    r"2\. Reputation check: .+\n"
    r"3\. Value-for-price: .+\n"
    r"4\. Final rationale: .+\n"
    r"Decision: (BUY|SKIP)$"
)


EVALUATION_CASES = [
    pytest.param(
        {
            "name": "high_relevance_high_reputation_buy",
            "query": "NSE NIFTY breakout scalp",
            "semantic_results": "[{\"relevance\": 94, \"reputation\": 88, \"price\": 5.0}]",
            "llm_output": "Reasoning:\n1. Relevance: 94 for NSE NIFTY breakout query.\n2. Reputation check: 88 which is above 50.\n3. Value-for-price: 18.8 (94/5.0).\n4. Final rationale: High relevance and strong reputation at fair price.\nDecision: BUY",
            "decision": "BUY",
        },
        id="high_relevance_high_reputation_buy",
    ),
    pytest.param(
        {
            "name": "low_reputation_skip",
            "query": "BankNifty intraday levels",
            "semantic_results": "[{\"relevance\": 92, \"reputation\": 42, \"price\": 3.0}]",
            "llm_output": "Reasoning:\n1. Relevance: 92 for the user intent.\n2. Reputation check: 42 which is below 50.\n3. Value-for-price: 30.67 but blocked by reputation rule.\n4. Final rationale: Reputation threshold not met.\nDecision: SKIP",
            "decision": "SKIP",
        },
        id="low_reputation_skip",
    ),
    pytest.param(
        {
            "name": "poor_value_for_price_skip",
            "query": "NSE swing idea",
            "semantic_results": "[{\"relevance\": 64, \"reputation\": 72, \"price\": 12.0}]",
            "llm_output": "Reasoning:\n1. Relevance: 64 moderate alignment.\n2. Reputation check: 72 above threshold.\n3. Value-for-price: 5.33 (64/12.0), below 8.0.\n4. Final rationale: Too expensive for the expected value.\nDecision: SKIP",
            "decision": "SKIP",
        },
        id="poor_value_for_price_skip",
    ),
    pytest.param(
        {
            "name": "nse_specific_relevance_buy",
            "query": "NSE FINNIFTY options gamma setup",
            "semantic_results": "[{\"relevance\": 90, \"reputation\": 79, \"price\": 6.0}]",
            "llm_output": "Reasoning:\n1. Relevance: 90 with explicit NSE FINNIFTY context match.\n2. Reputation check: 79 acceptable.\n3. Value-for-price: 15.0 (90/6.0).\n4. Final rationale: NSE-specific fit and good pricing.\nDecision: BUY",
            "decision": "BUY",
        },
        id="nse_specific_relevance_buy",
    ),
    pytest.param(
        {
            "name": "empty_search_results_skip",
            "query": "NSE metals breakout",
            "semantic_results": "[]",
            "llm_output": "Reasoning:\n1. Relevance: 0 because search returned no listings.\n2. Reputation check: No valid seller signal available.\n3. Value-for-price: 0 due to missing candidate insight.\n4. Final rationale: Cannot purchase without a retrievable result.\nDecision: SKIP",
            "decision": "SKIP",
        },
        id="empty_search_results_skip",
    ),
    pytest.param(
        {
            "name": "reputation_exactly_50_buy",
            "query": "NSE midcap swing",
            "semantic_results": "[{\"relevance\": 88, \"reputation\": 50, \"price\": 8.0}]",
            "llm_output": "Reasoning:\n1. Relevance: 88 suitable for NSE midcap setup.\n2. Reputation check: 50 meets the minimum threshold.\n3. Value-for-price: 11.0 (88/8.0).\n4. Final rationale: Borderline reputation but value rule passes.\nDecision: BUY",
            "decision": "BUY",
        },
        id="reputation_exactly_50_buy",
    ),
    pytest.param(
        {
            "name": "value_exactly_8_skip",
            "query": "NSE weekly expiry setup",
            "semantic_results": "[{\"relevance\": 80, \"reputation\": 77, \"price\": 10.0}]",
            "llm_output": "Reasoning:\n1. Relevance: 80 with acceptable topical match.\n2. Reputation check: 77 above minimum.\n3. Value-for-price: 8.0 equals threshold but does not exceed it.\n4. Final rationale: Rule requires strictly greater than 8.0.\nDecision: SKIP",
            "decision": "SKIP",
        },
        id="value_exactly_8_skip",
    ),
    pytest.param(
        {
            "name": "very_high_value_buy",
            "query": "NSE short-term call",
            "semantic_results": "[{\"relevance\": 96, \"reputation\": 70, \"price\": 4.0}]",
            "llm_output": "Reasoning:\n1. Relevance: 96 strong contextual fit.\n2. Reputation check: 70 is trusted.\n3. Value-for-price: 24.0 (96/4.0).\n4. Final rationale: Excellent expected value per USDC.\nDecision: BUY",
            "decision": "BUY",
        },
        id="very_high_value_buy",
    ),
    pytest.param(
        {
            "name": "high_price_low_value_skip",
            "query": "NSE positional hedge",
            "semantic_results": "[{\"relevance\": 78, \"reputation\": 90, \"price\": 20.0}]",
            "llm_output": "Reasoning:\n1. Relevance: 78 reasonable thematic match.\n2. Reputation check: 90 is high.\n3. Value-for-price: 3.9 (78/20.0), far below threshold.\n4. Final rationale: Cost is not justified by expected utility.\nDecision: SKIP",
            "decision": "SKIP",
        },
        id="high_price_low_value_skip",
    ),
    pytest.param(
        {
            "name": "nse_sector_specific_buy",
            "query": "NSE IT sector momentum setup",
            "semantic_results": "[{\"relevance\": 89, \"reputation\": 81, \"price\": 7.0}]",
            "llm_output": "Reasoning:\n1. Relevance: 89 with NSE IT sector-specific context.\n2. Reputation check: 81 comfortably above threshold.\n3. Value-for-price: 12.71 (89/7.0).\n4. Final rationale: Strong sector fit and favorable pricing.\nDecision: BUY",
            "decision": "BUY",
        },
        id="nse_sector_specific_buy",
    ),
    pytest.param(
        {
            "name": "low_relevance_skip",
            "query": "NSE overnight strategy",
            "semantic_results": "[{\"relevance\": 30, \"reputation\": 88, \"price\": 2.0}]",
            "llm_output": "Reasoning:\n1. Relevance: 30 weak match for the requested NSE setup.\n2. Reputation check: 88 is strong but cannot offset poor relevance.\n3. Value-for-price: 15.0 numerically high but quality signal is low.\n4. Final rationale: Relevance quality is insufficient to buy.\nDecision: SKIP",
            "decision": "SKIP",
        },
        id="low_relevance_skip",
    ),
    pytest.param(
        {
            "name": "multi_result_best_pick_buy",
            "query": "NSE options breakout",
            "semantic_results": "[{\"relevance\": 91, \"reputation\": 84, \"price\": 9.0},{\"relevance\": 75, \"reputation\": 76, \"price\": 5.0}]",
            "llm_output": "Reasoning:\n1. Relevance: 91 from the top-ranked NSE options result.\n2. Reputation check: 84 satisfies trust requirement.\n3. Value-for-price: 10.11 (91/9.0).\n4. Final rationale: Best candidate clears all buy thresholds.\nDecision: BUY",
            "decision": "BUY",
        },
        id="multi_result_best_pick_buy",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", EVALUATION_CASES)
async def test_evaluation_reasoning_and_decision_format(monkeypatch, case):
    invoke_mock = MagicMock(return_value=SimpleNamespace(content=case["llm_output"]))
    monkeypatch.setattr(agent_module, "llm", SimpleNamespace(invoke=invoke_mock))

    state = {
        "query": case["query"],
        "semantic_results": case["semantic_results"],
    }
    evaluated = await agent_module.evaluate_insights(state)

    assert evaluated["decision"] == case["decision"]
    assert evaluated["evaluation"] == case["llm_output"]
    assert EVALUATION_OUTPUT_PATTERN.fullmatch(evaluated["evaluation"]) is not None
    invoke_mock.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_x402_payment_success_after_approve(monkeypatch):
    buyer = os.getenv("DEPLOYER_ADDRESS", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM")
    seller = buyer
    listing_price_micro = 2_250_000

    listing = SimpleNamespace(seller=seller, price=listing_price_micro, ipfs_hash="QmCID")
    listing_client = SimpleNamespace(
        state=SimpleNamespace(
            box=SimpleNamespace(
                listings=SimpleNamespace(get_value=MagicMock(return_value=listing))
            )
        )
    )

    created_clients: list[SimpleNamespace] = []

    class FakeX402Client:
        def __init__(self, _algorand):
            self.simulate_payment = AsyncMock(return_value={"is_safe": True})
            self.send_micropayment = AsyncMock(return_value="TX402")
            self.ensure_asset_opt_in = MagicMock(return_value=None)
            created_clients.append(self)

    monkeypatch.setattr(x402_module, "USDC_ASA_ID", 10458941)
    monkeypatch.setattr(x402_module, "get_insight_listing_client", lambda: listing_client)
    monkeypatch.setattr(x402_module, "get_algorand_client", lambda: MagicMock())
    monkeypatch.setattr(x402_module, "X402Client", FakeX402Client)
    monkeypatch.setattr(
        x402_module,
        "complete_purchase_flow",
        AsyncMock(return_value="Insight delivered in full text"),
    )

    response = await x402_module.trigger_x402_payment.ainvoke(
        {
            "listing_id": 7,
            "buyer_address": buyer,
            "amount_usdc": 999.0,
            "user_approval_input": "approve",
        }
    )
    payload = json.loads(response)
    client = created_clients[0]

    assert payload["success"] is True
    assert payload["approved"] is True
    assert payload["transaction_id"] == "TX402"
    assert payload["payment_details"]["amount_usdc"] == 2.25
    assert payload["payment_details"]["settlement_asset_id"] == 10458941
    client.simulate_payment.assert_awaited_once_with(
        sender=buyer,
        receiver=seller,
        amount=listing_price_micro,
        asset_id=10458941,
    )
    client.send_micropayment.assert_awaited_once_with(
        sender=buyer,
        receiver=seller,
        amount=listing_price_micro,
        memo="Mercator insight purchase: listing 7",
        asset_id=10458941,
    )


@pytest.mark.asyncio
async def test_trigger_x402_payment_rejects_without_approval(monkeypatch):
    monkeypatch.setattr(x402_module, "get_insight_listing_client", MagicMock())

    response = await x402_module.trigger_x402_payment.ainvoke(
        {
            "listing_id": 1,
            "buyer_address": os.getenv("DEPLOYER_ADDRESS", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM"),
            "amount_usdc": 1.0,
            "user_approval_input": "",
        }
    )
    payload = json.loads(response)

    assert payload["success"] is False
    assert payload["approved"] is False
    assert payload["error"] == "APPROVAL_REQUIRED"


@pytest.mark.asyncio
async def test_trigger_x402_payment_simulation_failure(monkeypatch):
    buyer = os.getenv("DEPLOYER_ADDRESS", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM")
    listing = SimpleNamespace(seller=buyer, price=1_000_000, ipfs_hash="QmCID")
    listing_client = SimpleNamespace(
        state=SimpleNamespace(box=SimpleNamespace(listings=SimpleNamespace(get_value=MagicMock(return_value=listing))))
    )

    class UnsafeSimulationClient:
        def __init__(self, _algorand):
            self.simulate_payment = AsyncMock(return_value={"is_safe": False, "reason": "unsafe"})
            self.send_micropayment = AsyncMock(return_value="NEVER")
            self.ensure_asset_opt_in = MagicMock(return_value=None)

    monkeypatch.setattr(x402_module, "USDC_ASA_ID", 10458941)
    monkeypatch.setattr(x402_module, "get_insight_listing_client", lambda: listing_client)
    monkeypatch.setattr(x402_module, "get_algorand_client", lambda: MagicMock())
    monkeypatch.setattr(x402_module, "X402Client", UnsafeSimulationClient)

    response = await x402_module.trigger_x402_payment.ainvoke(
        {
            "listing_id": 3,
            "buyer_address": buyer,
            "amount_usdc": 1.0,
            "user_approval_input": "approve",
        }
    )
    payload = json.loads(response)

    assert payload["success"] is False
    assert payload["error"] == "SIMULATION_FAILED"


@pytest.mark.asyncio
async def test_trigger_x402_payment_insufficient_balance_edge(monkeypatch):
    buyer = os.getenv("DEPLOYER_ADDRESS", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM")
    listing = SimpleNamespace(seller=buyer, price=1_000_000, ipfs_hash="QmCID")
    listing_client = SimpleNamespace(
        state=SimpleNamespace(box=SimpleNamespace(listings=SimpleNamespace(get_value=MagicMock(return_value=listing))))
    )

    class InsufficientBalanceClient:
        def __init__(self, _algorand):
            self.simulate_payment = AsyncMock(side_effect=ValueError("insufficient balance"))
            self.send_micropayment = AsyncMock(return_value="NEVER")
            self.ensure_asset_opt_in = MagicMock(return_value=None)

    monkeypatch.setattr(x402_module, "USDC_ASA_ID", 10458941)
    monkeypatch.setattr(x402_module, "get_insight_listing_client", lambda: listing_client)
    monkeypatch.setattr(x402_module, "get_algorand_client", lambda: MagicMock())
    monkeypatch.setattr(x402_module, "X402Client", InsufficientBalanceClient)

    response = await x402_module.trigger_x402_payment.ainvoke(
        {
            "listing_id": 3,
            "buyer_address": buyer,
            "amount_usdc": 1.0,
            "user_approval_input": "approve",
        }
    )
    payload = json.loads(response)

    assert payload["success"] is False
    assert payload["error"] == "SIMULATION_ERROR"
    assert "insufficient balance" in payload["message"]


@pytest.mark.asyncio
async def test_trigger_x402_payment_listing_not_found(monkeypatch):
    buyer = os.getenv("DEPLOYER_ADDRESS", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM")
    listing_client = SimpleNamespace(
        state=SimpleNamespace(box=SimpleNamespace(listings=SimpleNamespace(get_value=MagicMock(return_value=None))))
    )

    monkeypatch.setattr(x402_module, "USDC_ASA_ID", 10458941)
    monkeypatch.setattr(x402_module, "get_insight_listing_client", lambda: listing_client)
    monkeypatch.setattr(x402_module, "get_algorand_client", lambda: MagicMock())

    response = await x402_module.trigger_x402_payment.ainvoke(
        {
            "listing_id": 999,
            "buyer_address": buyer,
            "amount_usdc": 1.0,
            "user_approval_input": "approve",
        }
    )
    payload = json.loads(response)

    assert payload["success"] is False
    assert payload["error"] == "LISTING_NOT_FOUND"


@pytest.mark.asyncio
async def test_trigger_x402_payment_invalid_buyer_address(monkeypatch):
    response = await x402_module.trigger_x402_payment.ainvoke(
        {
            "listing_id": 1,
            "buyer_address": "INVALID",
            "amount_usdc": 1.0,
            "user_approval_input": "approve",
        }
    )
    payload = json.loads(response)

    assert payload["success"] is False
    assert payload["error"] == "INVALID_ADDRESS"


@pytest.mark.asyncio
async def test_trigger_x402_payment_invalid_amount(monkeypatch):
    buyer = os.getenv("DEPLOYER_ADDRESS", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM")
    listing = SimpleNamespace(seller=buyer, price=1_000_000, ipfs_hash="QmCID")
    listing_client = SimpleNamespace(
        state=SimpleNamespace(box=SimpleNamespace(listings=SimpleNamespace(get_value=MagicMock(return_value=listing))))
    )

    monkeypatch.setattr(x402_module, "USDC_ASA_ID", 10458941)
    monkeypatch.setattr(x402_module, "get_insight_listing_client", lambda: listing_client)
    monkeypatch.setattr(x402_module, "get_algorand_client", lambda: MagicMock())

    response = await x402_module.trigger_x402_payment.ainvoke(
        {
            "listing_id": 2,
            "buyer_address": buyer,
            "amount_usdc": 0.0,
            "user_approval_input": "approve",
        }
    )
    payload = json.loads(response)

    assert payload["success"] is False
    assert payload["error"] == "INVALID_AMOUNT"


@pytest.mark.asyncio
async def test_trigger_x402_payment_execution_failure(monkeypatch):
    buyer = os.getenv("DEPLOYER_ADDRESS", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM")
    listing = SimpleNamespace(seller=buyer, price=1_000_000, ipfs_hash="QmCID")
    listing_client = SimpleNamespace(
        state=SimpleNamespace(box=SimpleNamespace(listings=SimpleNamespace(get_value=MagicMock(return_value=listing))))
    )

    class BrokenExecutionClient:
        def __init__(self, _algorand):
            self.simulate_payment = AsyncMock(return_value={"is_safe": True})
            self.send_micropayment = AsyncMock(side_effect=RuntimeError("network submission failed"))
            self.ensure_asset_opt_in = MagicMock(return_value=None)

    monkeypatch.setattr(x402_module, "USDC_ASA_ID", 10458941)
    monkeypatch.setattr(x402_module, "get_insight_listing_client", lambda: listing_client)
    monkeypatch.setattr(x402_module, "get_algorand_client", lambda: MagicMock())
    monkeypatch.setattr(x402_module, "X402Client", BrokenExecutionClient)

    response = await x402_module.trigger_x402_payment.ainvoke(
        {
            "listing_id": 2,
            "buyer_address": buyer,
            "amount_usdc": 1.0,
            "user_approval_input": "approve",
        }
    )
    payload = json.loads(response)

    assert payload["success"] is False
    assert payload["error"] == "PAYMENT_EXECUTION_FAILED"


@pytest.mark.asyncio
async def test_complete_purchase_flow_success_message_contains_full_insight(monkeypatch):
    buyer = os.getenv("DEPLOYER_ADDRESS", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM")
    insight_text = "Full premium insight text with exact entry, stop and targets"
    listing = SimpleNamespace(ipfs_hash="QmValidInsight")

    wait_mock = AsyncMock(side_effect=[12345, 12346])
    release_mock = MagicMock(return_value=SimpleNamespace(tx_id="ESCROW_TX"))
    fetch_mock = AsyncMock(return_value=insight_text)

    monkeypatch.setattr(post_payment_module, "_wait_for_confirmation", wait_mock)
    monkeypatch.setattr(
        post_payment_module,
        "escrow_client",
        SimpleNamespace(send=SimpleNamespace(release_after_payment=release_mock)),
    )
    monkeypatch.setattr(
        post_payment_module,
        "listing_client",
        SimpleNamespace(state=SimpleNamespace(box=SimpleNamespace(listings=SimpleNamespace(get_value=MagicMock(return_value=listing))))),
    )
    monkeypatch.setattr(post_payment_module, "fetch_insight_from_ipfs", fetch_mock)

    message = await post_payment_module.complete_purchase_flow(
        tx_id="PAY_TX",
        listing_id=9,
        buyer_wallet=buyer,
    )

    assert "Payment confirmed" in message
    assert "Escrow released" in message
    assert insight_text in message
    assert "payment=PAY_TX" in message
    assert "escrow=ESCROW_TX" in message


@pytest.mark.asyncio
async def test_complete_purchase_flow_confirmation_timeout(monkeypatch):
    monkeypatch.setattr(
        post_payment_module,
        "_wait_for_confirmation",
        AsyncMock(side_effect=RuntimeError("timed out waiting for confirmation")),
    )

    with pytest.raises(RuntimeError, match="timed out"):
        await post_payment_module.complete_purchase_flow(
            tx_id="PAY_TX",
            listing_id=1,
            buyer_wallet="buyer",
        )


@pytest.mark.asyncio
async def test_complete_purchase_flow_escrow_redeem_success(monkeypatch):
    buyer = os.getenv("DEPLOYER_ADDRESS", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM")
    listing = SimpleNamespace(ipfs_hash="QmValidInsight")

    release_mock = MagicMock(return_value=SimpleNamespace(tx_id="ESCROW_TX"))
    wait_mock = AsyncMock(side_effect=[12345, 12346])
    monkeypatch.setattr(post_payment_module, "_wait_for_confirmation", wait_mock)
    monkeypatch.setattr(
        post_payment_module,
        "escrow_client",
        SimpleNamespace(send=SimpleNamespace(release_after_payment=release_mock)),
    )
    monkeypatch.setattr(
        post_payment_module,
        "listing_client",
        SimpleNamespace(state=SimpleNamespace(box=SimpleNamespace(listings=SimpleNamespace(get_value=MagicMock(return_value=listing))))),
    )
    monkeypatch.setattr(post_payment_module, "fetch_insight_from_ipfs", AsyncMock(return_value="insight text"))

    message = await post_payment_module.complete_purchase_flow("PAY_TX", 2, buyer)

    release_mock.assert_called_once_with((buyer, 2))
    assert "Escrow released" in message


@pytest.mark.asyncio
async def test_complete_purchase_flow_escrow_redeem_failure_still_delivers(monkeypatch):
    buyer = os.getenv("DEPLOYER_ADDRESS", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM")
    listing = SimpleNamespace(ipfs_hash="QmValidInsight")

    monkeypatch.setattr(post_payment_module, "_wait_for_confirmation", AsyncMock(return_value=12345))
    monkeypatch.setattr(
        post_payment_module,
        "escrow_client",
        SimpleNamespace(send=SimpleNamespace(release_after_payment=MagicMock(side_effect=RuntimeError("guard reject")))),
    )
    monkeypatch.setattr(
        post_payment_module,
        "listing_client",
        SimpleNamespace(state=SimpleNamespace(box=SimpleNamespace(listings=SimpleNamespace(get_value=MagicMock(return_value=listing))))),
    )
    monkeypatch.setattr(post_payment_module, "fetch_insight_from_ipfs", AsyncMock(return_value="insight text"))

    message = await post_payment_module.complete_purchase_flow("PAY_TX", 2, buyer)

    assert "Escrow release skipped" in message
    assert "insight text" in message


@pytest.mark.asyncio
async def test_complete_purchase_flow_ipfs_fetch_failure(monkeypatch):
    buyer = os.getenv("DEPLOYER_ADDRESS", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM")
    listing = SimpleNamespace(ipfs_hash="QmBrokenCID")

    monkeypatch.setattr(post_payment_module, "_wait_for_confirmation", AsyncMock(return_value=12345))
    monkeypatch.setattr(
        post_payment_module,
        "escrow_client",
        SimpleNamespace(send=SimpleNamespace(release_after_payment=MagicMock(side_effect=RuntimeError("guard reject")))),
    )
    monkeypatch.setattr(
        post_payment_module,
        "listing_client",
        SimpleNamespace(state=SimpleNamespace(box=SimpleNamespace(listings=SimpleNamespace(get_value=MagicMock(return_value=listing))))),
    )
    monkeypatch.setattr(
        post_payment_module,
        "fetch_insight_from_ipfs",
        AsyncMock(side_effect=RuntimeError("ipfs unavailable")),
    )

    message = await post_payment_module.complete_purchase_flow("PAY_TX", 2, buyer)

    assert "could not be retrieved" in message


@pytest.mark.asyncio
async def test_complete_purchase_flow_listing_not_found(monkeypatch):
    buyer = os.getenv("DEPLOYER_ADDRESS", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM")

    monkeypatch.setattr(post_payment_module, "_wait_for_confirmation", AsyncMock(return_value=12345))
    monkeypatch.setattr(
        post_payment_module,
        "escrow_client",
        SimpleNamespace(send=SimpleNamespace(release_after_payment=MagicMock(side_effect=RuntimeError("guard reject")))),
    )
    monkeypatch.setattr(
        post_payment_module,
        "listing_client",
        SimpleNamespace(state=SimpleNamespace(box=SimpleNamespace(listings=SimpleNamespace(get_value=MagicMock(return_value=None))))),
    )

    with pytest.raises(RuntimeError, match="Listing 2 not found"):
        await post_payment_module.complete_purchase_flow("PAY_TX", 2, buyer)


@pytest.mark.asyncio
async def test_complete_purchase_flow_empty_tx_id_validation():
    with pytest.raises(ValueError, match="tx_id is required"):
        await post_payment_module.complete_purchase_flow("   ", 1, "buyer")


@pytest.mark.asyncio
async def test_complete_purchase_flow_negative_listing_validation():
    with pytest.raises(ValueError, match="listing_id must be non-negative"):
        await post_payment_module.complete_purchase_flow("PAY_TX", -1, "buyer")


@pytest.mark.asyncio
async def test_complete_purchase_flow_buyer_wallet_fallback(monkeypatch):
    monkeypatch.setattr(post_payment_module, "BUYER_WALLET", "FALLBACK_BUYER")
    monkeypatch.setattr(post_payment_module, "_wait_for_confirmation", AsyncMock(side_effect=RuntimeError("stop after fallback check")))

    with pytest.raises(RuntimeError, match="stop after fallback check"):
        await post_payment_module.complete_purchase_flow("PAY_TX", 1, "")


@pytest.mark.asyncio
async def test_complete_purchase_flow_missing_buyer_wallet_validation(monkeypatch):
    monkeypatch.setattr(post_payment_module, "BUYER_WALLET", "")
    with pytest.raises(ValueError, match="buyer_wallet is required"):
        await post_payment_module.complete_purchase_flow("PAY_TX", 1, "")


def _simulate_cycle_with_mocks(case: dict, delay_mock: MagicMock) -> str:
    if case["network_delay_seconds"] > 0:
        delay_mock(case["network_delay_seconds"])

    if case["reputation"] < 50:
        return "SKIP_LOW_REPUTATION"

    if case["insight_value"] == "low":
        return "SKIP_POOR_VALUE"

    if case["approval_input"] != "approve":
        return "APPROVAL_REQUIRED"

    if case["balance_state"] == "insufficient":
        return "PAYMENT_FAILED_INSUFFICIENT_BALANCE"

    if case["cid_state"] == "invalid":
        return "DELIVERY_FALLBACK_INVALID_CID"

    return "SUCCESS_FULL_DELIVERY"


def _expected_cycle_outcome(case: dict) -> str:
    if case["reputation"] < 50:
        return "SKIP_LOW_REPUTATION"
    if case["insight_value"] == "low":
        return "SKIP_POOR_VALUE"
    if case["approval_input"] != "approve":
        return "APPROVAL_REQUIRED"
    if case["balance_state"] == "insufficient":
        return "PAYMENT_FAILED_INSUFFICIENT_BALANCE"
    if case["cid_state"] == "invalid":
        return "DELIVERY_FALLBACK_INVALID_CID"
    return "SUCCESS_FULL_DELIVERY"


FULL_CYCLE_CASES = [
    pytest.param(
        {
            "reputation": reputation,
            "balance_state": balance_state,
            "network_delay_seconds": network_delay_seconds,
            "cid_state": cid_state,
            "insight_value": insight_value,
            "approval_input": approval_input,
        },
        id=(
            f"rep_{reputation}_bal_{balance_state}_delay_{network_delay_seconds}_"
            f"cid_{cid_state}_value_{insight_value}_approval_{approval_input}"
        ),
    )
    for reputation, balance_state, network_delay_seconds, cid_state, insight_value, approval_input in itertools.product(
        [40, 50, 90],
        ["sufficient", "insufficient"],
        [0.0, 0.02],
        ["valid", "invalid"],
        ["high", "low"],
        ["approve", "reject"],
    )
]


@pytest.mark.parametrize("case", FULL_CYCLE_CASES)
def test_full_micropayment_cycle(case):
    delay_mock = MagicMock(side_effect=lambda seconds: time.sleep(0))
    outcome = _simulate_cycle_with_mocks(case, delay_mock)
    expected = _expected_cycle_outcome(case)

    assert outcome == expected

    if case["network_delay_seconds"] > 0:
        delay_mock.assert_called_once_with(case["network_delay_seconds"])
    else:
        delay_mock.assert_not_called()
