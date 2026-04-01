"""Semantic search tool for ranking live on-chain listings."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from functools import lru_cache

import numpy as np
from algokit_utils import AlgorandClient
from algosdk import account as algo_account
from algosdk import mnemonic as algo_mnemonic
from algosdk.v2client import indexer
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from tenacity import retry, stop_after_attempt, wait_fixed

from contracts.insight_listing import InsightListingClient
from contracts.reputation import ReputationClient

try:
    from utils.ipfs import fetch_insight_from_ipfs, upload_insight_to_ipfs
except ImportError:  # pragma: no cover - supports running from repo root
    from backend.utils.ipfs import fetch_insight_from_ipfs, upload_insight_to_ipfs


load_dotenv()
load_dotenv(".env.testnet", override=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

embeddings = GoogleGenerativeAIEmbeddings(
    model="embedding-004",
    google_api_key=os.getenv("GEMINI_API_KEY"),
) if os.getenv("GEMINI_API_KEY") else None

_CACHE_TTL_SECONDS = 300
_query_cache: dict[str, tuple[float, str]] = {}


@lru_cache(maxsize=1)
def get_algorand_client() -> AlgorandClient:
    """Return a cached Algorand client configured from environment."""
    algod = AlgorandClient.from_environment()
    deployer_mnemonic = os.getenv("DEPLOYER_MNEMONIC", "").strip()
    deployer_address = os.getenv("DEPLOYER_ADDRESS", "").strip()
    if deployer_mnemonic and deployer_address:
        signer = algod.account.from_mnemonic(
            mnemonic=deployer_mnemonic,
            sender=deployer_address,
        )
        algod.set_default_signer(signer)
    return algod


@lru_cache(maxsize=1)
def get_insight_listing_client() -> InsightListingClient:
    """Return the deployed InsightListing app client."""
    app_id = int(os.getenv("INSIGHT_LISTING_APP_ID", "0"))
    if app_id <= 0:
        raise ValueError("INSIGHT_LISTING_APP_ID not configured")

    deployer_mnemonic = os.getenv("DEPLOYER_MNEMONIC", "").strip()
    sender = (
        algo_account.address_from_private_key(
            algo_mnemonic.to_private_key(deployer_mnemonic)
        )
        if deployer_mnemonic
        else os.getenv("DEPLOYER_ADDRESS", "").strip() or None
    )

    return InsightListingClient(
        algorand=get_algorand_client(),
        app_id=app_id,
        default_sender=sender,
    )


@lru_cache(maxsize=1)
def get_reputation_client() -> ReputationClient | None:
    """Return the deployed Reputation app client when configured."""
    app_id = int(os.getenv("REPUTATION_APP_ID", "0"))
    if app_id <= 0:
        return None

    deployer_mnemonic = os.getenv("DEPLOYER_MNEMONIC", "").strip()
    sender = (
        algo_account.address_from_private_key(
            algo_mnemonic.to_private_key(deployer_mnemonic)
        )
        if deployer_mnemonic
        else os.getenv("DEPLOYER_ADDRESS", "").strip() or None
    )

    return ReputationClient(
        algorand=get_algorand_client(),
        app_id=app_id,
        default_sender=sender,
    )


@lru_cache(maxsize=1)
def get_indexer_client() -> indexer.IndexerClient:
    """Return a cached indexer client instance for read operations."""
    token = os.getenv("ALGOD_TOKEN", "")
    idx_url = (
        os.getenv("INDEXER_URL")
        or os.getenv("INDEXER_SERVER")
        or "https://testnet-idx.algonode.cloud"
    )
    return indexer.IndexerClient(indexer_token=token, indexer_address=idx_url)


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def _embed_text(text: str) -> np.ndarray:
    """Embed text and return a dense vector with retry and rate-limit handling."""
    if embeddings is None:
        raise RuntimeError("GEMINI_API_KEY not configured for embeddings")
    try:
        vector = embeddings.embed_query(text)
    except Exception as err:  # pragma: no cover - network/API dependent
        message = str(err).lower()
        if "429" in message or "resource_exhausted" in message:
            logger.warning("Gemini embedding rate-limited (429); retrying")
            time.sleep(2)
        raise
    return np.array(vector, dtype=float)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator == 0.0:
        return 0.0
    return float(np.dot(a, b) / denominator)


def _reputation_score_for_seller(seller: str) -> float:
    """Fetch on-chain reputation score for a seller (0 when unavailable)."""
    rep_client = get_reputation_client()
    if rep_client is None:
        return 0.0

    try:
        score = rep_client.state.box.seller_scores.get_value(seller)
        if score is None:
            return 0.0
        return float(score)
    except Exception:
        return 0.0


@tool
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def semantic_search(query: str) -> str:
    """Run semantic ranking across live listings using relevance + reputation."""
    _ = upload_insight_to_ipfs
    _ = get_indexer_client()

    cleaned_query = query.strip()
    if not cleaned_query:
        return json.dumps({"query": query, "matches": [], "message": "Empty query"})

    cached = _query_cache.get(cleaned_query)
    if cached and (time.time() - cached[0]) < _CACHE_TTL_SECONDS:
        return cached[1]

    listings_map = get_insight_listing_client().state.box.listings.get_map()
    if not listings_map:
        result = json.dumps(
            {"query": cleaned_query, "matches": [], "message": "No active listings"},
            indent=2,
        )
        _query_cache[cleaned_query] = (time.time(), result)
        return result

    listing_entries: list[dict[str, object]] = []
    for listing_id, listing in listings_map.items():
        cid = str(listing.ipfs_hash)
        try:
            full_text = await fetch_insight_from_ipfs(cid)
        except Exception as err:  # pragma: no cover - network/API dependent
            logger.warning("Skipping CID %s due to fetch failure: %s", cid, err)
            continue

        reputation_score = _reputation_score_for_seller(str(listing.seller))
        listing_entries.append(
            {
                "listing_id": int(listing_id),
                "price": int(listing.price),
                "seller": str(listing.seller),
                "cid": cid,
                "asa_id": int(listing.asa_id),
                "reputation": reputation_score,
                "text": full_text,
            }
        )

    if not listing_entries:
        result = json.dumps(
            {
                "query": cleaned_query,
                "matches": [],
                "message": "No retrievable insights found",
            },
            indent=2,
        )
        _query_cache[cleaned_query] = (time.time(), result)
        return result

    embedding_fallback = False
    try:
        query_vector = await asyncio.to_thread(_embed_text, cleaned_query)
        for entry in listing_entries:
            entry_vector = await asyncio.to_thread(_embed_text, str(entry["text"]))
            entry["relevance"] = _cosine_similarity(query_vector, entry_vector)
    except Exception as err:  # pragma: no cover - network/API dependent
        message = str(err).lower()
        if "429" in message or "resource_exhausted" in message:
            logger.warning("Gemini rate limit during semantic_search; using fallback")
            await asyncio.sleep(2)
        else:
            logger.warning("Embedding failure during semantic_search: %s", err)

        embedding_fallback = True
        query_words = {w for w in cleaned_query.lower().split() if w}
        for entry in listing_entries:
            text_words = set(str(entry["text"]).lower().split())
            overlap = len(query_words & text_words)
            relevance = overlap / max(len(query_words), 1)
            entry["relevance"] = float(relevance)

    for entry in listing_entries:
        reputation_norm = min(max(float(entry["reputation"]), 0.0), 100.0) / 100.0
        weighted_score = 0.7 * float(entry["relevance"]) + 0.3 * reputation_norm
        entry["score"] = round(weighted_score, 6)

    ranked = sorted(listing_entries, key=lambda item: float(item["score"]), reverse=True)[:3]
    matches = [
        {
            "listing_id": item["listing_id"],
            "price_micro_usdc": item["price"],
            "price_usdc": round(float(item["price"]) / 1_000_000, 6),
            "reputation": item["reputation"],
            "cid": item["cid"],
            "asa_id": item["asa_id"],
            "score": item["score"],
            "insight_preview": str(item["text"])[:180],
        }
        for item in ranked
    ]

    result = json.dumps(
        {
            "query": cleaned_query,
            "embedding_fallback": embedding_fallback,
            "matches": matches,
        },
        indent=2,
    )
    _query_cache[cleaned_query] = (time.time(), result)
    return result


async def _main() -> None:
    """Standalone local test runner for this tool module."""
    if hasattr(semantic_search, "ainvoke"):
        result = await semantic_search.ainvoke(
            {"query": "latest NIFTY breakout pattern"}
        )
    else:
        result = await semantic_search("latest NIFTY breakout pattern")
    print(result)


if __name__ == "__main__":
    asyncio.run(_main())
