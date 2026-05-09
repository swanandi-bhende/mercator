from __future__ import annotations

import json
import math
import os
import importlib
from types import SimpleNamespace

import numpy as np
import pytest

os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("ALGOD_URL", "https://testnet-api.algonode.cloud")
os.environ.setdefault("INDEXER_URL", "https://testnet-idx.algonode.cloud")
os.environ.setdefault("ALGOD_SERVER", os.getenv("ALGOD_SERVER", os.getenv("ALGOD_URL", "https://testnet-api.algonode.cloud")))
os.environ.setdefault("INDEXER_SERVER", os.getenv("INDEXER_SERVER", os.getenv("INDEXER_URL", "https://testnet-idx.algonode.cloud")))

semantic_module = importlib.import_module("backend.tools.semantic_search")


@pytest.fixture(autouse=True)
def _reset_semantic_search_state(monkeypatch):
    semantic_module._embedding_cache.clear()
    semantic_module._query_cache.clear()
    semantic_module._listing_cache.clear()
    semantic_module._reputation_cache.clear()
    semantic_module.get_agent_registry_client.cache_clear()
    monkeypatch.setattr(semantic_module.tracer, "start_event", lambda *args, **kwargs: "event-1")
    monkeypatch.setattr(semantic_module.tracer, "resolve_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(semantic_module, "_resolve_seller_display_name_sync", lambda wallet: wallet)
    yield
    semantic_module._embedding_cache.clear()
    semantic_module._query_cache.clear()
    semantic_module._listing_cache.clear()
    semantic_module._reputation_cache.clear()
    semantic_module.get_agent_registry_client.cache_clear()


def _normalized_vector(similarity: float, dimension: int = 768) -> np.ndarray:
    vector = np.zeros(dimension, dtype=float)
    vector[0] = similarity
    vector[1] = math.sqrt(max(0.0, 1.0 - similarity**2))
    return vector


def _fake_llm(message: str = "Relevant in one sentence.") -> SimpleNamespace:
    return SimpleNamespace(invoke=lambda prompt: SimpleNamespace(content=message))


def _fake_embedding_lookup(mapping: dict[str, np.ndarray]):
    def _embed_query(self, text: str) -> list[float]:
        vector = mapping.get(text)
        if vector is None:
            raise AssertionError(f"Unexpected embedding request: {text}")
        return vector.tolist()

    return _embed_query


def _listing(listing_id: int, seller_wallet: str, source_type: str, text: str, price_usdc: float = 2.0) -> semantic_module.RawListing:
    return semantic_module.RawListing(
        listing_id=listing_id,
        seller_wallet=seller_wallet,
        price_micro_usdc=int(price_usdc * 1_000_000),
        asa_id=1000 + listing_id,
        cid=f"cid-{listing_id}",
        text=text,
        source_type=source_type,
    )


def test_mmr_produces_diverse_results():
    query = _normalized_vector(1.0)
    listings = np.array(
        [
            _normalized_vector(0.97),
            _normalized_vector(0.97),
            _normalized_vector(0.60),
            _normalized_vector(0.60),
            _normalized_vector(0.20),
        ]
    )

    selected = semantic_module.mmr_rerank(query, listings, 3, 0.1)

    assert len(selected) == 3
    assert not ({0, 1} <= set(selected))


def test_mmr_is_deterministic():
    query = _normalized_vector(1.0)
    listings = np.array(
        [
            _normalized_vector(0.95),
            _normalized_vector(0.60),
            _normalized_vector(0.60),
            _normalized_vector(0.20),
        ]
    )

    first = semantic_module.mmr_rerank(query, listings, 3, 0.7)
    second = semantic_module.mmr_rerank(query, listings, 3, 0.7)

    assert first == second


def test_mmr_first_selection_is_most_relevant():
    query = _normalized_vector(1.0)
    listings = np.array(
        [
            _normalized_vector(0.60),
            _normalized_vector(0.95),
            _normalized_vector(0.60),
            _normalized_vector(0.60),
        ]
    )

    selected = semantic_module.mmr_rerank(query, listings, 3, 0.7)

    assert selected[0] == 1


@pytest.mark.asyncio
async def test_low_reputation_listings_filtered_before_embedding(monkeypatch):
    listings = [
        _listing(1, "wallet-low-1", "curator_agent", "low-1"),
        _listing(2, "wallet-low-2", "curator_agent", "low-2"),
        _listing(3, "wallet-low-3", "curator_agent", "low-3"),
        _listing(4, "wallet-high-1", "curator_agent", "high-1"),
        _listing(5, "wallet-high-2", "curator_agent", "high-2"),
    ]
    async def _fetch_all_active_listings():
        return listings

    async def _reputation(seller_wallet: str) -> float:
        return 30.0 if seller_wallet.startswith("wallet-low") else 75.0

    vectors = {
        "NIFTY": _normalized_vector(1.0),
        "low-1": _normalized_vector(0.95),
        "low-2": _normalized_vector(0.95),
        "low-3": _normalized_vector(0.95),
        "high-1": _normalized_vector(0.60),
        "high-2": _normalized_vector(0.60),
    }
    monkeypatch.setattr(semantic_module, "fetch_all_active_listings", _fetch_all_active_listings)
    monkeypatch.setattr(semantic_module, "_fetch_reputation_for_seller", _reputation)
    monkeypatch.setattr(type(semantic_module._embeddings_model), "embed_query", _fake_embedding_lookup(vectors))
    monkeypatch.setattr(semantic_module, "get_relevance_llm", lambda: _fake_llm())

    raw = await semantic_module.semantic_search.ainvoke({"query": "NIFTY", "min_reputation": 50, "limit": 3})
    parsed = json.loads(raw)

    assert parsed["metrics"]["embeddings_computed"] == 2
    assert len(parsed["results"]) == 2


@pytest.mark.asyncio
async def test_empty_results_returns_helpful_message(monkeypatch):
    listings = [
        _listing(1, "wallet-low-1", "curator_agent", "low-1"),
        _listing(2, "wallet-low-2", "curator_agent", "low-2"),
    ]

    async def _fetch_all_active_listings():
        return listings

    async def _reputation(_seller_wallet: str) -> float:
        return 20.0

    monkeypatch.setattr(semantic_module, "fetch_all_active_listings", _fetch_all_active_listings)
    monkeypatch.setattr(semantic_module, "_fetch_reputation_for_seller", _reputation)

    message = await semantic_module.semantic_search.ainvoke({"query": "NIFTY", "min_reputation": 50})

    assert "No listings found" in message


@pytest.mark.asyncio
async def test_cache_hit_on_second_call(monkeypatch):
    listings = [
        _listing(1, "wallet-high-1", "curator_agent", "high-1"),
        _listing(2, "wallet-high-2", "curator_agent", "high-2"),
    ]

    async def _fetch_all_active_listings():
        return listings

    async def _reputation(_seller_wallet: str) -> float:
        return 75.0

    vectors = {
        "NIFTY": _normalized_vector(1.0),
        "high-1": _normalized_vector(0.60),
        "high-2": _normalized_vector(0.20),
    }
    monkeypatch.setattr(semantic_module, "fetch_all_active_listings", _fetch_all_active_listings)
    monkeypatch.setattr(semantic_module, "_fetch_reputation_for_seller", _reputation)
    monkeypatch.setattr(type(semantic_module._embeddings_model), "embed_query", _fake_embedding_lookup(vectors))
    monkeypatch.setattr(semantic_module, "get_relevance_llm", lambda: _fake_llm())

    first_raw = await semantic_module.semantic_search.ainvoke({"query": "NIFTY", "min_reputation": 50, "limit": 2})
    first_parsed = json.loads(first_raw)
    second_raw = await semantic_module.semantic_search.ainvoke({"query": "NIFTY", "min_reputation": 50, "limit": 2})
    second_parsed = json.loads(second_raw)

    assert second_parsed["metrics"]["embeddings_from_cache"] == first_parsed["metrics"]["embeddings_computed"]


@pytest.mark.asyncio
async def test_source_type_filter_isolates_curator(monkeypatch):
    listings = [
        _listing(1, "wallet-curator-1", "curator_agent", "curator-1"),
        _listing(2, "wallet-curator-2", "curator_agent", "curator-2"),
        _listing(3, "wallet-other-1", "seller", "seller-1"),
    ]

    async def _fetch_all_active_listings():
        return listings

    async def _reputation(_seller_wallet: str) -> float:
        return 75.0

    vectors = {
        "NIFTY": _normalized_vector(1.0),
        "curator-1": _normalized_vector(0.95),
        "curator-2": _normalized_vector(0.60),
        "seller-1": _normalized_vector(0.20),
    }
    monkeypatch.setattr(semantic_module, "fetch_all_active_listings", _fetch_all_active_listings)
    monkeypatch.setattr(semantic_module, "_fetch_reputation_for_seller", _reputation)
    monkeypatch.setattr(type(semantic_module._embeddings_model), "embed_query", _fake_embedding_lookup(vectors))
    monkeypatch.setattr(semantic_module, "get_relevance_llm", lambda: _fake_llm())

    raw = await semantic_module.semantic_search.ainvoke({"query": "NIFTY", "min_reputation": 50, "source_type": "curator_agent"})
    parsed = json.loads(raw)

    assert parsed["results"]
    assert all(result["source_type"] == "curator_agent" for result in parsed["results"])
