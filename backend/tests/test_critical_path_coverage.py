"""Critical path reliability tests for Mercator backend.

Purpose: Validate failure handling and guardrails across core micropayment path modules.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import logging
import os
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_module_with_env(module_file: Path, module_name: str, monkeypatch, env: dict[str, str]) -> object:
    for key in [
        "INDEXER_URL",
        "INDEXER_SERVER",
        "ESCROW_APP_ID",
        "INSIGHT_LISTING_APP_ID",
        "BUYER_WALLET",
        "BUYER_MNEMONIC",
        "DEPLOYER_ADDRESS",
        "DEPLOYER_MNEMONIC",
    ]:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    spec = importlib.util.spec_from_file_location(module_name, str(module_file))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def main_module():
    return importlib.import_module("backend.main")


@pytest.fixture()
def agent_module():
    return importlib.import_module("backend.agent")


@pytest.fixture()
def semantic_module():
    return importlib.import_module("backend.tools.semantic_search")


@pytest.fixture()
def x402_module():
    return importlib.import_module("backend.tools.x402_payment")


@pytest.fixture()
def post_module():
    return importlib.import_module("backend.tools.post_payment_flow")


def test_main_helpers_and_branches(main_module, monkeypatch):
    original_handlers = list(main_module.logger.handlers)
    main_module.logger.handlers = [logging.NullHandler()]
    main_module._configure_logging()

    monkeypatch.delenv("ALGOD_URL", raising=False)
    monkeypatch.delenv("ALGOD_SERVER", raising=False)
    monkeypatch.setattr(main_module, "normalize_network_env", lambda: None)
    with pytest.raises(HTTPException):
        main_module._get_algod_client()

    monkeypatch.setenv("ALGOD_URL", "https://example.algod")
    monkeypatch.setenv("ALGOD_TOKEN", "tok")
    algod_client_ctor = MagicMock(return_value=SimpleNamespace())
    monkeypatch.setattr(main_module.algod, "AlgodClient", algod_client_ctor)
    main_module._get_algod_client()
    algod_client_ctor.assert_called_once()

    monkeypatch.delenv("INDEXER_URL", raising=False)
    monkeypatch.delenv("INDEXER_SERVER", raising=False)
    with pytest.raises(HTTPException):
        main_module._get_indexer_client()

    monkeypatch.setenv("INDEXER_URL", "https://example.indexer")
    indexer_ctor = MagicMock(return_value=SimpleNamespace())
    monkeypatch.setattr(main_module.indexer, "IndexerClient", indexer_ctor)
    main_module._get_indexer_client()
    indexer_ctor.assert_called_once()
    main_module.logger.handlers = original_handlers


def test_main_funding_and_signing(main_module, monkeypatch):
    client = MagicMock()
    client.account_info.return_value = {"min-balance": 100_000, "amount": 0}
    client.suggested_params.return_value = SimpleNamespace(flat_fee=False)
    client.send_transaction.return_value = "TX"

    monkeypatch.setattr(main_module, "_get_algod_client", lambda: client)
    monkeypatch.setattr(main_module, "get_application_address", lambda app_id: "APPADDR")
    monkeypatch.setattr(main_module.mnemonic, "to_private_key", lambda m: "PRIV")
    monkeypatch.setattr(main_module.transaction, "PaymentTxn", MagicMock(return_value=SimpleNamespace(sign=lambda _: "SIGNED")))
    monkeypatch.setattr(main_module.transaction, "wait_for_confirmation", MagicMock(return_value={"confirmed-round": 1}))

    monkeypatch.delenv("DEPLOYER_MNEMONIC", raising=False)
    with pytest.raises(HTTPException):
        main_module._ensure_listing_app_funded(10)

    monkeypatch.setenv("DEPLOYER_MNEMONIC", "mnemonic")
    main_module._ensure_listing_app_funded(10)


def test_main_misc_paths(main_module, monkeypatch):
    monkeypatch.setattr(main_module, "warn_missing_required_env", MagicMock())
    main_module.startup_checks()

    assert main_module._extract_final_insight_text({"payment_status": {"post_payment_output": "x"}}) == "x"
    assert main_module._extract_final_insight_text({}) == ""
    rich = "Here is your human trading insight:\n\nTEXT\n\nTransaction IDs: payment=abc"
    assert main_module._extract_final_insight_text({"payment_status": {"post_payment_output": rich}}) == "TEXT"

    idx = MagicMock()
    idx.search_transactions.return_value = {
        "transactions": [
            {"application-transaction": {"application-args": [None]}},
            {"id": "FOUND", "application-transaction": {"application-args": ["Y2lkLTEyMw=="]}},
        ]
    }
    monkeypatch.setattr(main_module, "_get_indexer_client", lambda: idx)
    assert main_module._find_cid_tx_id(1, "sender", "cid-123") == "FOUND"
    assert main_module._find_cid_tx_id(1, "sender", "missing") is None

    async def _poll_timeout():
        monkeypatch.setattr(main_module, "_find_cid_tx_id", lambda *_args, **_kwargs: None)
        with pytest.raises(HTTPException):
            await main_module._poll_for_listing_confirmation(app_id=1, sender="s", cid="c", max_seconds=1)

    asyncio.run(_poll_timeout())

    async def _poll_success():
        monkeypatch.setattr(main_module, "_find_cid_tx_id", lambda *_args, **_kwargs: "TXID")
        tx = await main_module._poll_for_listing_confirmation(app_id=1, sender="s", cid="c", max_seconds=1)
        assert tx == "TXID"

    asyncio.run(_poll_success())

    monkeypatch.delenv("SELLER_MNEMONIC", raising=False)
    monkeypatch.delenv("DEPLOYER_MNEMONIC", raising=False)
    with pytest.raises(HTTPException):
        main_module._get_signing_mnemonic()

    assert main_module.health() == {"status": "ok"}


@pytest.mark.asyncio
async def test_main_demo_purchase_and_invalid_listing_paths(main_module, monkeypatch):
    payload = main_module.DemoPurchaseRequest(user_query="q")
    monkeypatch.setattr(main_module, "run_agent", AsyncMock(return_value={"success": True, "payment_status": {"post_payment_output": "ok"}}))
    out = await main_module.demo_purchase(payload)
    assert out["success"] is True

    req = main_module.ListingRequest(
        insight_text="hello",
        price=1.0,
        seller_wallet=os.getenv("DEPLOYER_ADDRESS", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM"),
    )

    monkeypatch.setattr(main_module, "_ensure_listing_app_funded", MagicMock())
    monkeypatch.setattr(main_module, "upload_insight_to_ipfs", AsyncMock(return_value="cid"))
    monkeypatch.setattr(main_module, "store_cid_in_listing", MagicMock(return_value=(1, 2)))
    monkeypatch.setattr(main_module, "_poll_for_listing_confirmation", AsyncMock(return_value="tx"))
    monkeypatch.setattr(main_module, "_get_signing_mnemonic", lambda: "m")
    monkeypatch.setattr(main_module.mnemonic, "to_private_key", lambda _m: "p")
    monkeypatch.setattr(main_module.account, "address_from_private_key", lambda _p: req.seller_wallet)

    original_getenv = os.getenv
    monkeypatch.setattr(main_module.os, "getenv", lambda key, default="": "" if key == "INSIGHT_LISTING_APP_ID" else original_getenv(key, default))
    with pytest.raises(HTTPException):
        await main_module.create_listing(req)

    monkeypatch.setattr(main_module.os, "getenv", lambda key, default="": "bad" if key == "INSIGHT_LISTING_APP_ID" else original_getenv(key, default))
    with pytest.raises(HTTPException):
        await main_module.create_listing(req)

    monkeypatch.setattr(main_module.os, "getenv", lambda key, default="": "1" if key == "INSIGHT_LISTING_APP_ID" else original_getenv(key, default))
    monkeypatch.setattr(main_module.account, "address_from_private_key", lambda _p: "DIFFERENT")
    with pytest.raises(HTTPException):
        await main_module.create_listing(req)


def test_agent_parse_and_evaluate_branches(agent_module, monkeypatch):
    parser_mock = MagicMock()
    parser_mock.parse.return_value = SimpleNamespace(decision="buy")
    monkeypatch.setattr(agent_module, "decision_parser", parser_mock)
    assert agent_module._parse_decision("anything") == "BUY"

    parser_mock.parse.side_effect = ValueError("x")
    assert agent_module._parse_decision("no decision") == "SKIP"


@pytest.mark.asyncio
async def test_agent_evaluate_exception_branches(agent_module, monkeypatch):
    monkeypatch.setattr(agent_module, "llm", SimpleNamespace(invoke=MagicMock(side_effect=RuntimeError("boom"))))
    with pytest.raises(RuntimeError):
        await agent_module.evaluate_insights({"query": "q", "semantic_results": "[]"})

    monkeypatch.setattr(agent_module, "llm", SimpleNamespace(invoke=MagicMock(side_effect=RuntimeError("429 TooManyRequests"))))
    out = await agent_module.evaluate_insights({"query": "q", "semantic_results": "[]"})
    assert out["decision"] == "SKIP"


@pytest.mark.asyncio
async def test_agent_run_agent_paths(agent_module, monkeypatch):
    monkeypatch.setattr(agent_module, "semantic_search_tool", SimpleNamespace(ainvoke=AsyncMock(return_value="[]")))
    monkeypatch.setattr(agent_module, "evaluate_insights", AsyncMock(return_value={"decision": "SKIP", "evaluation": "e"}))
    out = await agent_module.run_agent("q")
    assert out["decision"] == "SKIP"

    monkeypatch.setattr(agent_module, "evaluate_insights", AsyncMock(return_value={"decision": "BUY", "evaluation": "e"}))
    pending = await agent_module.run_agent("q", user_approval_input="")
    assert pending["decision"] == "BUY_PENDING_APPROVAL"

    monkeypatch.setattr(agent_module, "trigger_x402_payment", SimpleNamespace(ainvoke=AsyncMock(return_value="not-json")))
    buy_out = await agent_module.run_agent("q", user_approval_input="approve", buyer_address="BUYER", force_buy_for_test=True)
    assert buy_out["decision"] == "BUY"

    monkeypatch.setattr(agent_module, "trigger_x402_payment", SimpleNamespace(ainvoke=AsyncMock(side_effect=RuntimeError("pay error"))))
    err_out = await agent_module.run_agent("q", user_approval_input="approve", buyer_address="BUYER", force_buy_for_test=True)
    assert err_out["success"] is False


@pytest.mark.asyncio
async def test_agent_executor_retry_and_fallbacks(agent_module, monkeypatch):
    monkeypatch.setattr(agent_module, "semantic_search_tool", SimpleNamespace(ainvoke=AsyncMock(return_value="[]")))
    monkeypatch.setattr(agent_module, "evaluate_insights", AsyncMock(return_value={"decision": "OTHER", "evaluation": "e"}))

    class FailingExecutor:
        def __init__(self, messages):
            self._messages = messages
            self.calls = 0

        def invoke(self, _payload):
            msg = self._messages[self.calls]
            self.calls += 1
            if isinstance(msg, Exception):
                raise msg
            return msg

    sleep_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(agent_module.asyncio, "sleep", sleep_mock)

    quota_exec = FailingExecutor([
        RuntimeError("429 TooManyRequests"),
        RuntimeError("RESOURCE_EXHAUSTED"),
        RuntimeError("429 again"),
    ])
    monkeypatch.setattr(agent_module, "agent_executor", quota_exec)
    out = await agent_module.run_agent("q")
    assert out["fallback"] is True

    model_exec = FailingExecutor([RuntimeError("404 NOT_FOUND")])
    monkeypatch.setattr(agent_module, "agent_executor", model_exec)
    out2 = await agent_module.run_agent("q")
    assert out2["fallback"] is True

    generic_exec = FailingExecutor([RuntimeError("generic")])
    monkeypatch.setattr(agent_module, "agent_executor", generic_exec)
    with pytest.raises(RuntimeError):
        await agent_module.run_agent("q")


def test_agent_misc_entrypoints(agent_module, monkeypatch):
    assert agent_module.on_chain_query.invoke({"listing_id": 10}) == "on_chain_query placeholder: listing_id=10."

    run_mock = MagicMock(return_value={"decision": "BUY", "message": "ok", "payment_status": "paid"})
    monkeypatch.setattr(agent_module.asyncio, "run", run_mock)
    runpy.run_module("backend.agent", run_name="__main__")


def test_agent_module_import_time_branches(monkeypatch):
    module_path = REPO_ROOT / "backend" / "agent.py"
    backup = dict(sys.modules)

    fake_agents = SimpleNamespace(
        create_tool_calling_agent=lambda *_a, **_k: "agent",
        AgentExecutor=lambda **_k: "exec",
        create_agent=lambda **_k: "compat",
    )
    sys.modules["langchain.agents"] = fake_agents  # type: ignore[assignment]

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    spec = importlib.util.spec_from_file_location("agent_missing_key", str(module_path))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    monkeypatch.setenv("GEMINI_API_KEY", "k")
    spec2 = importlib.util.spec_from_file_location("agent_with_tool_calling", str(module_path))
    module2 = importlib.util.module_from_spec(spec2)
    assert spec2 and spec2.loader
    spec2.loader.exec_module(module2)
    assert getattr(module2, "agent_executor") == "exec"

    sys.modules.clear()
    sys.modules.update(backup)


def test_agent_import_raises_without_key_when_dotenv_does_not_populate(monkeypatch):
    module_path = REPO_ROOT / "backend" / "agent.py"
    spec = importlib.util.spec_from_file_location("agent_missing_key_strict", str(module_path))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    original_getenv = os.getenv
    monkeypatch.setattr(os, "getenv", lambda key, default=None: "" if key == "GEMINI_API_KEY" else original_getenv(key, default))
    original_load_dotenv = sys.modules["dotenv"].load_dotenv
    monkeypatch.setattr(sys.modules["dotenv"], "load_dotenv", lambda *_a, **_k: False)
    with pytest.raises(ValueError):
        spec.loader.exec_module(module)
    monkeypatch.setattr(sys.modules["dotenv"], "load_dotenv", original_load_dotenv)
    monkeypatch.setattr(os, "getenv", original_getenv)


def test_semantic_helper_paths(semantic_module, monkeypatch):
    semantic_module.get_algorand_client.cache_clear()
    semantic_module.get_insight_listing_client.cache_clear()
    semantic_module.get_reputation_client.cache_clear()
    semantic_module.get_indexer_client.cache_clear()

    alg = SimpleNamespace(account=SimpleNamespace(from_mnemonic=MagicMock(return_value="signer")), set_default_signer=MagicMock())
    monkeypatch.setattr(semantic_module.AlgorandClient, "from_environment", MagicMock(return_value=alg))

    monkeypatch.setenv("DEPLOYER_MNEMONIC", "m")
    monkeypatch.setenv("DEPLOYER_ADDRESS", "A")
    semantic_module.get_algorand_client()

    original_getenv = os.getenv
    monkeypatch.setattr(semantic_module.os, "getenv", lambda key, default="": "0" if key == "INSIGHT_LISTING_APP_ID" else original_getenv(key, default))
    with pytest.raises(ValueError):
        semantic_module.get_insight_listing_client()

    monkeypatch.setattr(semantic_module.os, "getenv", original_getenv)
    monkeypatch.setenv("INSIGHT_LISTING_APP_ID", "1")
    monkeypatch.setattr(semantic_module, "InsightListingClient", MagicMock(return_value=SimpleNamespace()))
    semantic_module.get_insight_listing_client.cache_clear()
    semantic_module.get_insight_listing_client()

    monkeypatch.setattr(semantic_module.os, "getenv", lambda key, default="": "0" if key == "REPUTATION_APP_ID" else original_getenv(key, default))
    semantic_module.get_reputation_client.cache_clear()
    assert semantic_module.get_reputation_client() is None

    monkeypatch.setattr(semantic_module.os, "getenv", original_getenv)
    monkeypatch.setenv("REPUTATION_APP_ID", "1")
    monkeypatch.setattr(semantic_module, "ReputationClient", MagicMock(return_value=SimpleNamespace(state=SimpleNamespace(box=SimpleNamespace(seller_scores=SimpleNamespace(get_value=lambda _s: 1))))))
    semantic_module.get_reputation_client.cache_clear()
    semantic_module.get_reputation_client()

    monkeypatch.delenv("INDEXER_URL", raising=False)
    monkeypatch.delenv("INDEXER_SERVER", raising=False)
    monkeypatch.setattr(semantic_module.indexer, "IndexerClient", MagicMock(return_value=SimpleNamespace()))
    semantic_module.get_indexer_client.cache_clear()
    semantic_module.get_indexer_client()


def test_semantic_embedding_and_reputation(semantic_module, monkeypatch):
    monkeypatch.setattr(semantic_module, "embeddings", None)
    with pytest.raises(Exception):
        semantic_module._embed_text("q")

    monkeypatch.setattr(semantic_module, "embeddings", SimpleNamespace(embed_query=MagicMock(side_effect=RuntimeError("429 rate limit"))))
    monkeypatch.setattr(semantic_module.time, "sleep", MagicMock())
    with pytest.raises(Exception):
        semantic_module._embed_text("q")

    monkeypatch.setattr(semantic_module, "embeddings", SimpleNamespace(embed_query=MagicMock(return_value=[1.0, 2.0])))
    assert semantic_module._embed_text("ok").shape == (2,)
    assert semantic_module._cosine_similarity(semantic_module.np.array([0.0, 0.0]), semantic_module.np.array([1.0, 0.0])) == 0.0

    monkeypatch.setattr(semantic_module, "get_reputation_client", lambda: None)
    assert semantic_module._reputation_score_for_seller("s") == 0.0

    failing_client = SimpleNamespace(state=SimpleNamespace(box=SimpleNamespace(seller_scores=SimpleNamespace(get_value=MagicMock(side_effect=RuntimeError("fail"))))))
    monkeypatch.setattr(semantic_module, "get_reputation_client", lambda: failing_client)
    assert semantic_module._reputation_score_for_seller("s") == 0.0

    none_client = SimpleNamespace(state=SimpleNamespace(box=SimpleNamespace(seller_scores=SimpleNamespace(get_value=MagicMock(return_value=None)))))
    monkeypatch.setattr(semantic_module, "get_reputation_client", lambda: none_client)
    assert semantic_module._reputation_score_for_seller("s") == 0.0


@pytest.mark.asyncio
async def test_semantic_search_extra_branches_and_main(semantic_module, monkeypatch):
    semantic_module._query_cache.clear()
    monkeypatch.setattr(semantic_module, "get_indexer_client", lambda: SimpleNamespace())
    monkeypatch.setattr(semantic_module, "get_insight_listing_client", lambda: SimpleNamespace(state=SimpleNamespace(box=SimpleNamespace(listings=SimpleNamespace(get_map=lambda: {})))))
    out = await semantic_module.semantic_search.ainvoke({"query": "   "})
    assert "Empty query" in out

    out2 = await semantic_module.semantic_search.ainvoke({"query": "abc"})
    assert "No active listings" in out2

    semantic_module._query_cache.clear()
    listings = {1: SimpleNamespace(ipfs_hash="cid", seller="s", price=1_000_000, asa_id=1)}
    monkeypatch.setattr(semantic_module, "get_insight_listing_client", lambda: SimpleNamespace(state=SimpleNamespace(box=SimpleNamespace(listings=SimpleNamespace(get_map=lambda: listings)))))
    monkeypatch.setattr(semantic_module, "fetch_insight_from_ipfs", AsyncMock(side_effect=RuntimeError("bad cid")))
    out3 = await semantic_module.semantic_search.ainvoke({"query": "abc"})
    assert "No retrievable insights found" in out3

    monkeypatch.setattr(semantic_module, "semantic_search", SimpleNamespace(ainvoke=AsyncMock(return_value="ok")))
    await semantic_module._main()

    async def _callable_without_ainvoke(_query: str):
        return "ok"

    monkeypatch.setattr(semantic_module, "semantic_search", _callable_without_ainvoke)
    await semantic_module._main()


def test_semantic_module_main_entry(monkeypatch):
    run_mock = MagicMock(return_value=None)
    monkeypatch.setattr(asyncio, "run", run_mock)
    runpy.run_module("backend.tools.semantic_search", run_name="__main__")


def test_x402_client_helper_branches(x402_module, monkeypatch):
    x402_module.get_algorand_client.cache_clear()
    x402_module.get_insight_listing_client.cache_clear()
    x402_module.get_escrow_client.cache_clear()
    x402_module.get_reputation_client.cache_clear()

    alg = SimpleNamespace(account=SimpleNamespace(from_mnemonic=MagicMock(return_value="signer")), set_default_signer=MagicMock())
    monkeypatch.setattr(x402_module.AlgorandClient, "from_environment", MagicMock(return_value=alg))

    monkeypatch.setenv("DEPLOYER_MNEMONIC", "m")
    monkeypatch.setenv("DEPLOYER_ADDRESS", "A")
    x402_module.get_algorand_client()

    original_getenv = os.getenv
    monkeypatch.setattr(x402_module.os, "getenv", lambda key, default="": "0" if key == "INSIGHT_LISTING_APP_ID" else original_getenv(key, default))
    with pytest.raises(ValueError):
        x402_module.get_insight_listing_client()

    monkeypatch.setattr(x402_module.os, "getenv", original_getenv)
    monkeypatch.setenv("INSIGHT_LISTING_APP_ID", "1")
    monkeypatch.setattr(x402_module, "InsightListingClient", MagicMock(return_value=SimpleNamespace()))
    x402_module.get_insight_listing_client.cache_clear()
    x402_module.get_insight_listing_client()

    monkeypatch.setattr(x402_module.os, "getenv", lambda key, default="": "0" if key == "ESCROW_APP_ID" else original_getenv(key, default))
    with pytest.raises(ValueError):
        x402_module.get_escrow_client()

    monkeypatch.setattr(x402_module.os, "getenv", original_getenv)
    monkeypatch.setenv("ESCROW_APP_ID", "1")
    monkeypatch.setattr(x402_module, "EscrowClient", MagicMock(return_value=SimpleNamespace()))
    x402_module.get_escrow_client.cache_clear()
    x402_module.get_escrow_client()

    monkeypatch.setattr(x402_module.os, "getenv", lambda key, default="": "0" if key == "REPUTATION_APP_ID" else original_getenv(key, default))
    with pytest.raises(ValueError):
        x402_module.get_reputation_client()

    monkeypatch.setattr(x402_module.os, "getenv", original_getenv)
    monkeypatch.setenv("REPUTATION_APP_ID", "1")
    monkeypatch.setattr(x402_module, "ReputationClient", MagicMock(return_value=SimpleNamespace()))
    x402_module.get_reputation_client.cache_clear()
    x402_module.get_reputation_client()


@pytest.mark.asyncio
async def test_x402_client_methods_and_validate(x402_module, monkeypatch):
    algod_client = MagicMock()
    algod_client.account_info.return_value = {"assets": []}
    algod_client.suggested_params.return_value = SimpleNamespace(flat_fee=True)
    algod_client.send_transaction.return_value = "TX"

    client = x402_module.X402Client(SimpleNamespace(client=SimpleNamespace(algod=algod_client)))

    with pytest.raises(ValueError):
        client._resolve_private_key_for_sender("")

    monkeypatch.setenv("BUYER_MNEMONIC", "m")
    monkeypatch.setenv("BUYER_WALLET", "ADDR")
    monkeypatch.setenv("DEPLOYER_ADDRESS", "ADDR")
    monkeypatch.setenv("DEPLOYER_MNEMONIC", "m")
    monkeypatch.setattr(x402_module.algo_mnemonic, "to_private_key", lambda _m: "PRIV")
    monkeypatch.setattr(x402_module.algo_account, "address_from_private_key", lambda _p: "ADDR")
    assert client._resolve_private_key_for_sender("ADDR") == "PRIV"

    monkeypatch.setattr(x402_module.algo_account, "address_from_private_key", lambda _p: "OTHER")
    with pytest.raises(ValueError):
        client._resolve_private_key_for_sender("ADDR")

    monkeypatch.setenv("BUYER_MNEMONIC", "")
    monkeypatch.setenv("BUYER_WALLET", "ADDR")
    monkeypatch.setenv("DEPLOYER_MNEMONIC", "")
    monkeypatch.setenv("DEPLOYER_ADDRESS", "")
    with pytest.raises(ValueError):
        client._resolve_private_key_for_sender("ADDR")

    monkeypatch.setenv("BUYER_MNEMONIC", "m")
    monkeypatch.setenv("BUYER_WALLET", "OTHER_ADDR")
    monkeypatch.setenv("DEPLOYER_MNEMONIC", "")
    monkeypatch.setenv("DEPLOYER_ADDRESS", "")
    with pytest.raises(ValueError):
        client._resolve_private_key_for_sender("ADDR")

    monkeypatch.setenv("DEPLOYER_ADDRESS", "ADDR")
    monkeypatch.setenv("DEPLOYER_MNEMONIC", "m")

    monkeypatch.setattr(x402_module.transaction, "AssetTransferTxn", MagicMock(return_value=SimpleNamespace(sign=lambda _pk: "SIGNED")))
    monkeypatch.setattr(x402_module.transaction, "wait_for_confirmation", MagicMock(return_value={"confirmed-round": 1}))
    assert client.ensure_asset_opt_in("ADDR", 1) == "TX"
    assert client.ensure_asset_opt_in("ADDR", 0) is None

    algod_client.account_info.return_value = {"assets": [{"asset-id": 1}]}
    assert client.ensure_asset_opt_in("ADDR", 1) is None

    algod_client.account_info.side_effect = RuntimeError("indexer down")
    monkeypatch.setenv("DEPLOYER_ADDRESS", "DIFFERENT")
    monkeypatch.setenv("DEPLOYER_MNEMONIC", "")
    assert client.ensure_asset_opt_in("ADDR", 1) is None
    algod_client.account_info.side_effect = None

    monkeypatch.setattr(x402_module.encoding, "is_valid_address", lambda a: a == "OK")
    monkeypatch.setattr(x402_module, "PaymentTxn", lambda **_kwargs: SimpleNamespace())
    with pytest.raises(ValueError):
        await client.simulate_payment("BAD", "OK", 1, 0)

    with pytest.raises(ValueError):
        await client.simulate_payment("OK", "BAD", 1, 0)

    ok = await client.simulate_payment("OK", "OK", 1, 0)
    assert ok["success"] is True

    monkeypatch.setattr(
        x402_module.transaction,
        "AssetTransferTxn",
        MagicMock(return_value=SimpleNamespace()),
    )
    ok_asa = await client.simulate_payment("OK", "OK", 2, 7)
    assert ok_asa["asset_id"] == 7

    monkeypatch.setattr(x402_module.PaymentTxn, "__call__", lambda *args, **kwargs: None)
    monkeypatch.setattr(x402_module.transaction, "wait_for_confirmation", MagicMock(return_value={"confirmed-round": 1}))
    monkeypatch.setattr(client, "_resolve_private_key_for_sender", lambda _s: "PRIV")

    class DummyTxn:
        note = b""

        def sign(self, _pk):
            return "SIGNED"

    monkeypatch.setattr(x402_module, "PaymentTxn", lambda **_kwargs: DummyTxn())
    txid = await client.send_micropayment("OK", "OK", 1, memo="m", asset_id=0)
    assert txid == "TX"

    monkeypatch.setattr(
        x402_module.transaction,
        "AssetTransferTxn",
        MagicMock(return_value=DummyTxn()),
    )
    txid2 = await client.send_micropayment("OK", "OK", 1, memo="m", asset_id=7)
    assert txid2 == "TX"

    monkeypatch.setattr(client, "_resolve_private_key_for_sender", lambda _s: (_ for _ in ()).throw(RuntimeError("sign fail")))
    with pytest.raises(Exception):
        await client.send_micropayment("OK", "OK", 1, asset_id=0)

    monkeypatch.setattr(x402_module, "get_algorand_client", lambda: SimpleNamespace(client=SimpleNamespace(algod=SimpleNamespace(pending_transaction_info=lambda _tx: {"confirmed-round": 0}))))
    pending = json.loads(await x402_module.validate_x402_payment.ainvoke({"transaction_id": "TX"}))
    assert pending["confirmed"] is False

    monkeypatch.setattr(x402_module, "get_algorand_client", lambda: SimpleNamespace(client=SimpleNamespace(algod=SimpleNamespace(pending_transaction_info=lambda _tx: {"confirmed-round": 5}))))
    done = json.loads(await x402_module.validate_x402_payment.ainvoke({"transaction_id": "TX"}))
    assert done["confirmed"] is True

    def _explode(_tx):
        raise RuntimeError("idx")

    monkeypatch.setattr(x402_module, "get_algorand_client", lambda: SimpleNamespace(client=SimpleNamespace(algod=SimpleNamespace(pending_transaction_info=_explode))))
    fallback = json.loads(await x402_module.validate_x402_payment.ainvoke({"transaction_id": "TX"}))
    assert fallback["success"] is True

    monkeypatch.setattr(x402_module, "get_algorand_client", lambda: (_ for _ in ()).throw(RuntimeError("outer")))
    failed = json.loads(await x402_module.validate_x402_payment.ainvoke({"transaction_id": "TX"}))
    assert failed["success"] is False


@pytest.mark.asyncio
async def test_x402_trigger_outer_error_branch(x402_module, monkeypatch):
    monkeypatch.setattr(x402_module, "normalize_network_env", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    payload = json.loads(
        await x402_module.trigger_x402_payment.ainvoke(
            {
                "listing_id": 1,
                "buyer_address": "ADDR",
                "amount_usdc": 1.0,
                "user_approval_input": "approve",
            }
        )
    )
    assert payload["error"] == "SYSTEM_ERROR"


@pytest.mark.asyncio
async def test_x402_trigger_usdc_not_configured_branch(x402_module, monkeypatch):
    buyer = os.getenv("DEPLOYER_ADDRESS", "M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM")
    listing = SimpleNamespace(seller=buyer, price=1_000_000, ipfs_hash="QmCID")
    listing_client = SimpleNamespace(state=SimpleNamespace(box=SimpleNamespace(listings=SimpleNamespace(get_value=MagicMock(return_value=listing)))))

    monkeypatch.setattr(x402_module, "USDC_ASA_ID", 0)
    monkeypatch.setattr(x402_module, "get_insight_listing_client", lambda: listing_client)
    monkeypatch.setattr(x402_module, "get_algorand_client", lambda: MagicMock())
    monkeypatch.setattr(x402_module.encoding, "is_valid_address", lambda _a: True)

    payload = json.loads(
        await x402_module.trigger_x402_payment.ainvoke(
            {
                "listing_id": 1,
                "buyer_address": buyer,
                "amount_usdc": 1.0,
                "user_approval_input": "approve",
            }
        )
    )
    assert payload["error"] == "USDC_ASA_ID_NOT_CONFIGURED"


def test_post_payment_import_guard_branches_with_stubbed_runtime(monkeypatch):
    module_file = REPO_ROOT / "backend" / "tools" / "post_payment_flow.py"
    runtime_stub = SimpleNamespace(configure_demo_logging=lambda: MagicMock(), normalize_network_env=lambda: None)
    backup_runtime = sys.modules.get("backend.utils.runtime_env")
    sys.modules["backend.utils.runtime_env"] = runtime_stub  # type: ignore[assignment]

    with pytest.raises(ValueError):
        _load_module_with_env(module_file, "tmp_post_guard_idx", monkeypatch, {"ESCROW_APP_ID": "1", "INSIGHT_LISTING_APP_ID": "1"})
    with pytest.raises(ValueError):
        _load_module_with_env(module_file, "tmp_post_guard_esc", monkeypatch, {"INDEXER_URL": "https://idx", "INSIGHT_LISTING_APP_ID": "1"})
    with pytest.raises(ValueError):
        _load_module_with_env(module_file, "tmp_post_guard_listing", monkeypatch, {"INDEXER_URL": "https://idx", "ESCROW_APP_ID": "1"})

    if backup_runtime is None:
        del sys.modules["backend.utils.runtime_env"]
    else:
        sys.modules["backend.utils.runtime_env"] = backup_runtime


def test_post_payment_import_guards(monkeypatch):
    module_file = REPO_ROOT / "backend" / "tools" / "post_payment_flow.py"
    loaded = _load_module_with_env(
        module_file,
        "tmp_post_loaded",
        monkeypatch,
        {
            "INDEXER_URL": "https://idx",
            "ESCROW_APP_ID": "1",
            "INSIGHT_LISTING_APP_ID": "1",
        },
    )
    assert hasattr(loaded, "complete_purchase_flow")


def test_post_payment_helpers(post_module, monkeypatch):
    post_module.get_escrow_client.cache_clear()
    post_module.get_listing_client.cache_clear()

    alg = SimpleNamespace(account=SimpleNamespace(from_mnemonic=MagicMock(return_value="signer")), set_default_signer=MagicMock())
    monkeypatch.setattr(post_module.AlgorandClient, "from_environment", MagicMock(return_value=alg))
    monkeypatch.setattr(post_module, "EscrowClient", MagicMock(return_value=SimpleNamespace()))
    monkeypatch.setattr(post_module, "InsightListingClient", MagicMock(return_value=SimpleNamespace()))

    monkeypatch.setattr(post_module, "BUYER_MNEMONIC", "")
    monkeypatch.setattr(post_module, "BUYER_WALLET", "")
    monkeypatch.setenv("DEPLOYER_MNEMONIC", "")
    monkeypatch.setenv("DEPLOYER_ADDRESS", "")

    post_module.get_escrow_client()
    post_module.get_listing_client()

    assert post_module._extract_tx_id(SimpleNamespace(tx_id="TX")) == "TX"
    assert post_module._extract_tx_id(SimpleNamespace(tx_ids=["TX2"])) == "TX2"

    class TObj:
        def get_txid(self):
            return "TX3"

    assert post_module._extract_tx_id(SimpleNamespace(transaction=TObj())) == "TX3"
    with pytest.raises(RuntimeError):
        post_module._extract_tx_id(SimpleNamespace())


@pytest.mark.asyncio
async def test_post_payment_wait_and_tool(post_module, monkeypatch):
    post_module.indexer_client = SimpleNamespace(transaction=lambda _tx: {"transaction": {"confirmed-round": "7"}})
    assert await post_module._wait_for_confirmation("TX", timeout_seconds=1) == 7

    post_module.indexer_client = SimpleNamespace(transaction=lambda _tx: {"transaction": {"confirmed-round": 0}})
    sleep_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(post_module.asyncio, "sleep", sleep_mock)

    with pytest.raises(RuntimeError):
        await post_module._wait_for_confirmation("TX", timeout_seconds=0)

    monkeypatch.setattr(post_module, "complete_purchase_flow", AsyncMock(return_value="done"))
    assert await post_module.complete_purchase_flow_tool.ainvoke({"tx_id": "TX", "listing_id": 1, "buyer_wallet": "B"}) == "done"


def test_post_payment_no_signer_constructor_paths(post_module, monkeypatch):
    post_module.get_escrow_client.cache_clear()
    post_module.get_listing_client.cache_clear()

    alg = SimpleNamespace(account=SimpleNamespace(from_mnemonic=MagicMock(return_value="signer")), set_default_signer=MagicMock())
    monkeypatch.setattr(post_module.AlgorandClient, "from_environment", MagicMock(return_value=alg))
    escrow_ctor = MagicMock(return_value=SimpleNamespace())
    listing_ctor = MagicMock(return_value=SimpleNamespace())
    monkeypatch.setattr(post_module, "EscrowClient", escrow_ctor)
    monkeypatch.setattr(post_module, "InsightListingClient", listing_ctor)

    monkeypatch.setattr(post_module, "BUYER_MNEMONIC", "")
    monkeypatch.setattr(post_module, "BUYER_WALLET", "")
    monkeypatch.setenv("DEPLOYER_MNEMONIC", "")
    monkeypatch.setenv("DEPLOYER_ADDRESS", "")

    original_getenv = post_module.os.getenv
    monkeypatch.setattr(
        post_module.os,
        "getenv",
        lambda key, default="": "" if key in {"DEPLOYER_MNEMONIC", "DEPLOYER_ADDRESS"} else original_getenv(key, default),
    )

    post_module.get_escrow_client()
    post_module.get_listing_client()
    assert "default_sender" not in escrow_ctor.call_args.kwargs
    assert "default_sender" not in listing_ctor.call_args.kwargs


@pytest.mark.asyncio
async def test_post_payment_wait_for_confirmation_exception_branch(post_module, monkeypatch):
    post_module.indexer_client = SimpleNamespace(transaction=MagicMock(side_effect=RuntimeError("temporary")))
    monkeypatch.setattr(post_module.asyncio, "sleep", AsyncMock(return_value=None))

    timeline = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr(post_module.time, "time", lambda: next(timeline))

    with pytest.raises(RuntimeError):
        await post_module._wait_for_confirmation("TX", timeout_seconds=1)


@pytest.mark.asyncio
async def test_agent_buy_parsing_and_tool_payload_branches(agent_module, monkeypatch):
    listing_json = '[{"listing_id": "7", "price": "2.5"}]'
    monkeypatch.setattr(agent_module, "semantic_search_tool", SimpleNamespace(ainvoke=AsyncMock(return_value=listing_json)))
    monkeypatch.setattr(agent_module, "evaluate_insights", AsyncMock(return_value={"decision": "BUY", "evaluation": "eval"}))
    monkeypatch.delenv("BUYER_WALLET", raising=False)
    monkeypatch.setenv("BUYER_ADDRESS", "ADDR_FROM_ENV")

    trigger = AsyncMock(return_value={"success": False, "tx": "T"})
    monkeypatch.setattr(agent_module, "trigger_x402_payment", SimpleNamespace(ainvoke=trigger))

    out = await agent_module.run_agent("q", user_approval_input="approve", buyer_address="")
    assert out["success"] is False
    called_payload = trigger.await_args.args[0]
    assert called_payload["listing_id"] == 7
    assert called_payload["amount_usdc"] == 2.5
    assert called_payload["buyer_address"] == "ADDR_FROM_ENV"


@pytest.mark.asyncio
async def test_agent_executor_payload_and_result_merge_branches(agent_module, monkeypatch):
    monkeypatch.setattr(agent_module, "semantic_search_tool", SimpleNamespace(ainvoke=AsyncMock(return_value="[]")))

    class DecisionSwitcher(dict):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def get(self, key, default=None):
            if key == "evaluation":
                return "eval"
            if key == "decision":
                self.calls += 1
                return "OTHER" if self.calls <= 2 else "BUY"
            return default

    monkeypatch.setattr(agent_module, "evaluate_insights", AsyncMock(return_value=DecisionSwitcher()))
    monkeypatch.setattr(agent_module, "create_tool_calling_agent", object())
    monkeypatch.setattr(agent_module, "AgentExecutor", object())
    monkeypatch.setattr(agent_module, "agent_executor", SimpleNamespace(invoke=lambda _payload: {"ok": True}))

    out = await agent_module.run_agent("q", user_approval=False)
    assert out["evaluation"] == "eval"
    assert out["decision"] == "BUY"
