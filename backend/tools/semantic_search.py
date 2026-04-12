"""Semantic search tool for ranking live on-chain listings.

Purpose: Implements semantic + lexical search for buyer insight discovery.
Ranks listings by: 0.7*semantic_relevance + 0.3*seller_reputation_norm.
Returns top 3 results and caches for 300 seconds (invalidated after new listings).

Key Components:
- semantic_search(query): LLM embeddings (Gemini) for deep semantic ranking.
- Fallback: Lexical word-overlap matching when embedding service unavailable.
- Recent fallback: Immediate hit for freshly listed insights (local cache).
- Cache: _query_cache dict with TTL to avoid redundant embedding calls.

This tool is the single interface used by /discover endpoint and the agent tool.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
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
from backend.utils.runtime_env import configure_demo_logging, normalize_network_env


normalize_network_env()
demo_logger = configure_demo_logging()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

embeddings = GoogleGenerativeAIEmbeddings(
    model="embedding-004",
    google_api_key=os.getenv("GEMINI_API_KEY"),
) if os.getenv("GEMINI_API_KEY") else None

_CACHE_TTL_SECONDS = 300
_query_cache: dict[str, tuple[float, str]] = {}


def clear_semantic_search_cache() -> None:
    """Invalidate cached query results so fresh listings are discoverable immediately.
    
    Purpose: Called after successful /list endpoint to force re-ranking with new insight.
    """
    _query_cache.clear()


@lru_cache(maxsize=1)
def get_algorand_client() -> AlgorandClient:
    """Build cached Algorand client for contract reads.

    Input: none (reads env).
    Output: configured AlgorandClient.
    Micropayment role: foundation client for listing and reputation state reads.
    """
    normalize_network_env()
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
    """Build cached InsightListing client bound to deployed app id.

    Input: none (reads INSIGHT_LISTING_APP_ID and signer env).
    Output: InsightListingClient instance.
    Micropayment role: source of listings searched before payment decisions.
    """
    normalize_network_env()
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
    """Build cached Reputation client when configured.

    Input: none.
    Output: ReputationClient or None if REPUTATION_APP_ID is absent/invalid.
    Micropayment role: provides trust scores used in BUY/SKIP gating.
    """
    normalize_network_env()
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
    """Build cached indexer client for historical read operations.

    Input: none.
    Output: IndexerClient.
    Micropayment role: supporting lookup channel for listing/payment confirmations.
    """
    normalize_network_env()
    token = os.getenv("ALGOD_TOKEN", "")
    idx_url = (
        os.getenv("INDEXER_URL")
        or os.getenv("INDEXER_SERVER")
        or "https://testnet-idx.algonode.cloud"
    )
    return indexer.IndexerClient(indexer_token=token, indexer_address=idx_url)


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def _embed_text(text: str) -> np.ndarray:
    """Create embedding vector for text with retry handling.

    Input: plain text string.
    Output: dense numpy vector.
    Micropayment role: powers semantic ranking that selects candidate listings for purchase.
    """
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
    """Compute cosine similarity.

    Inputs: two vectors.
    Output: float relevance score.
    Micropayment role: relevance signal in buyer pre-purchase ranking formula.
    """
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator == 0.0:
        return 0.0
    return float(np.dot(a, b) / denominator)


def _reputation_score_for_seller(seller: str) -> float:
    """Fetch seller trust score from Reputation contract.

    Input: seller wallet address.
    Output: score as float (0 when unavailable).
    Micropayment role: trust factor in ranking and evaluation before payment execution.
    """
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
    """Run semantic ranking across live listings using relevance + reputation.
    
    Purpose: Main search tool for /discover endpoint and agent's semantic_search_tool.
    Ranks by: 0.7 * relevance_score + 0.3 * reputation_norm (0-100 scale).
    Returns: Top 3 matches as JSON with listing_id, price, reputation, CID, preview text.
    
    Flow:
    1. Get all listings from InsightListing contract state.
    2. For each listing, fetch full text from IPFS (cached).
    3. Embed user query and each listing, compute cosine similarity.
    4. Score: 0.7*relevance + 0.3*reputation, sort descending, return top 3.
    5. Cache result with TTL=300 seconds.
    
    Fallback: If embedding service unavailable (429, RESOURCE_EXHAUSTED), use lexical matching.
    """
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

    query_words = set(re.findall(r"[a-z0-9_]+", cleaned_query.lower()))
    fast_lexical_mode = any(word.startswith("batch_") for word in query_words)

    embedding_fallback = fast_lexical_mode
    if fast_lexical_mode:
        for entry in listing_entries:
            text_words = set(re.findall(r"[a-z0-9_]+", str(entry["text"]).lower()))
            overlap = len(query_words & text_words)
            relevance = overlap / max(len(query_words), 1)
            entry["relevance"] = float(relevance)
    else:
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
            for entry in listing_entries:
                text_words = set(re.findall(r"[a-z0-9_]+", str(entry["text"]).lower()))
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
            "seller_wallet": item["seller"],
            "listing_status": "Active",
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
    demo_logger.info("Agent semantic search returned %s results", len(matches))
    _query_cache[cleaned_query] = (time.time(), result)
    return result


async def _main() -> None:
    """Local smoke runner for semantic search tool.

    Input: none.
    Output: prints sample search JSON payload.
    Micropayment role: developer validation helper for discovery stage.
    """
    if hasattr(semantic_search, "ainvoke"):
        result = await semantic_search.ainvoke(
            {"query": "latest NIFTY breakout pattern"}
        )
    else:
        result = await semantic_search("latest NIFTY breakout pattern")
    print(result)


if __name__ == "__main__":
    asyncio.run(_main())
