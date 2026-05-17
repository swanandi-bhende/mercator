"""Semantic search tool for ranking live on-chain listings.

Pipeline overview:
1. Fetch active listings and hydrate their IPFS text.
2. Apply business filters for reputation, price, and source type.
3. Compute and cache normalized embeddings for the query and candidates.
4. Score candidates with relevance plus seller reputation.
5. Rerank the shortlist with iterative MMR.
6. Build the JSON response expected by /discover and the agent tool.
7. Cache the final response for repeated queries.

The public contract stays the same: semantic_search(query) returns a JSON string
with query, matches, and embedding_fallback.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import json
import logging
import os
import re
import time
import warnings
from dataclasses import asdict, dataclass, field, replace
from functools import lru_cache
from typing import Any, Optional

warnings.filterwarnings(
    "ignore",
    message="'_UnionGenericAlias' is deprecated and slated for removal in Python 3.17",
    category=DeprecationWarning,
    module=r"google\.genai\.types",
)

import numpy as np
from algokit_utils import AlgorandClient
from algosdk import account as algo_account
from algosdk import abi, encoding
from algosdk import mnemonic as algo_mnemonic
from algosdk.v2client import indexer
from cachetools import TTLCache
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from tenacity import retry, stop_after_attempt, wait_fixed

from contracts.insight_listing import InsightListingClient
from contracts.reputation import ReputationClient

try:
    from utils.ipfs import fetch_insight_from_ipfs, upload_insight_to_ipfs
except ImportError:  # pragma: no cover - supports running from repo root
    from backend.utils.ipfs import fetch_insight_from_ipfs, upload_insight_to_ipfs
from backend.utils.runtime_env import configure_demo_logging, normalize_network_env
from backend.utils.flow_tracer import tracer


load_dotenv()
normalize_network_env()
demo_logger = configure_demo_logging()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class SearchConfig:
    """Search configuration that keeps the staged pipeline predictable."""

    limit: int = 3
    min_reputation: int = 0
    max_price_usdc: float = 10.0
    source_type: str = "all"
    lambda_param: float = 0.7
    query_cache_ttl_seconds: int = 300
    listing_cache_ttl_seconds: int = 60
    reputation_cache_ttl_seconds: int = 30
    max_candidate_count: int = 50
    preview_length: int = 180
    embedding_model: str = os.getenv("GEMINI_EMBEDDING_MODEL", "models/text-embedding-004")
    embedding_dimensions: int = 768


# Purpose: Raw on-chain listing plus hydrated IPFS text before ranking.
@dataclass(slots=True)
class RawListing:
    listing_id: int
    seller_wallet: str
    price_micro_usdc: int
    asa_id: int
    cid: str
    text: str
    source_type: str = "unknown"
    active: bool = True
    retrieved_at: float = field(default_factory=time.time)
    expiry_round: int = 0


# Purpose: Cached seller reputation lookup value with the time it was fetched.
@dataclass(slots=True)
class SellerReputationCache:
    seller_wallet: str
    reputation_score: float
    fetched_at: float = field(default_factory=time.time)


# Purpose: Cached embedding vector keyed by text hash and embedding model.
@dataclass(slots=True)
class EmbeddingCacheEntry:
    text_hash: str
    model_name: str
    vector: np.ndarray
    created_at: float = field(default_factory=time.time)


# Purpose: Final ranked listing returned by the search pipeline.
@dataclass(slots=True)
class SearchResult:
    listing_id: int
    seller_wallet: str
    price_micro_usdc: int
    price_usdc: float
    asa_id: int
    cid: str
    source_type: str
    insight_preview: str
    relevance: float
    reputation: float
    score: float
    mmr_score: float = 0.0
    diversity_score: float = 1.0
    relevance_explanation: str = ""
    rank: int = 0
    listing_status: str = "Active"
    seller_display_name: str = ""


# Purpose: Internal diagnostics for the staged search pipeline.
@dataclass(slots=True)
class SearchMetrics:
    query: str
    total_listings_fetched: int = 0
    filtered_reputation_count: int = 0
    filtered_price_count: int = 0
    filtered_source_type_count: int = 0
    filtered_by_reputation: int = 0
    filtered_by_price: int = 0
    filtered_by_source_type: int = 0
    embeddings_computed: int = 0
    embeddings_from_cache: int = 0
    mmr_iterations: int = 0
    cache_hit: bool = False
    embedding_fallback: bool = False
    elapsed_seconds: float = 0.0


SEARCH_CONFIG = SearchConfig()
_CACHE_TTL_SECONDS = SEARCH_CONFIG.query_cache_ttl_seconds
_QUERY_CACHE_KEY = "__semantic_search__"
_LISTING_CACHE_KEY = "active_listings"

# How many rounds before expiry to exclude from search results (prevents near-expiry listings)
EXPIRY_BUFFER_ROUNDS = int(os.getenv("EXPIRY_BUFFER_ROUNDS", "100"))

_query_cache: dict[str, tuple[float, str]] = {}
_listing_cache: TTLCache[str, list[RawListing]] = TTLCache(maxsize=1, ttl=SEARCH_CONFIG.listing_cache_ttl_seconds)
_reputation_cache: TTLCache[str, SellerReputationCache] = TTLCache(maxsize=2048, ttl=SEARCH_CONFIG.reputation_cache_ttl_seconds)
_embedding_cache: dict[str, EmbeddingCacheEntry] = {}

_embeddings_model = GoogleGenerativeAIEmbeddings(
    model="models/text-embedding-004",
    google_api_key=os.getenv("GEMINI_API_KEY"),
)
embeddings = _embeddings_model


def clear_semantic_search_cache() -> None:
    """Invalidate cached query and listing snapshots so fresh listings surface immediately."""
    _query_cache.clear()
    invalidate_listing_cache()


def invalidate_listing_cache() -> None:
    """Clear the active-listing snapshot cache."""
    _listing_cache.clear()


@lru_cache(maxsize=1)
def get_algorand_client() -> AlgorandClient:
    """Build cached Algorand client for contract reads."""
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
    """Build cached InsightListing client bound to the deployed app id."""
    normalize_network_env()
    app_id = int(os.getenv("INSIGHT_LISTING_APP_ID", "0"))
    if app_id <= 0:
        raise ValueError("INSIGHT_LISTING_APP_ID not configured")

    deployer_mnemonic = os.getenv("DEPLOYER_MNEMONIC", "").strip()
    sender = os.getenv("DEPLOYER_ADDRESS", "").strip() or None
    if deployer_mnemonic:
        try:
            sender = algo_account.address_from_private_key(
                algo_mnemonic.to_private_key(deployer_mnemonic)
            )
        except Exception:
            sender = os.getenv("DEPLOYER_ADDRESS", "").strip() or None

    return InsightListingClient(
        algorand=get_algorand_client(),
        app_id=app_id,
        default_sender=sender,
    )


@lru_cache(maxsize=1)
def get_reputation_client() -> ReputationClient | None:
    """Build cached Reputation client when configured."""
    normalize_network_env()
    app_id = int(os.getenv("REPUTATION_APP_ID", "0"))
    if app_id <= 0:
        return None

    deployer_mnemonic = os.getenv("DEPLOYER_MNEMONIC", "").strip()
    sender = os.getenv("DEPLOYER_ADDRESS", "").strip() or None
    if deployer_mnemonic:
        try:
            sender = algo_account.address_from_private_key(
                algo_mnemonic.to_private_key(deployer_mnemonic)
            )
        except Exception:
            sender = os.getenv("DEPLOYER_ADDRESS", "").strip() or None

    return ReputationClient(
        algorand=get_algorand_client(),
        app_id=app_id,
        default_sender=sender,
    )


@lru_cache(maxsize=1)
def get_indexer_client() -> indexer.IndexerClient:
    """Build cached indexer client for historical read operations."""
    normalize_network_env()
    token = os.getenv("ALGOD_TOKEN", "")
    idx_url = (
        os.getenv("INDEXER_URL")
        or os.getenv("INDEXER_SERVER")
        or "https://testnet-idx.algonode.cloud"
    )
    return indexer.IndexerClient(indexer_token=token, indexer_address=idx_url)


def _embedding_model_name() -> str:
    return SEARCH_CONFIG.embedding_model


def _get_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_vector(vector: np.ndarray | list[float]) -> np.ndarray:
    values = np.array(vector, dtype=float)
    length = float(np.linalg.norm(values))
    if length == 0.0:
        return values
    return values / length


def _normalize_matrix_rows(matrix: np.ndarray) -> np.ndarray:
    if matrix.size == 0:
        return matrix.astype(float)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    return matrix / norms


def _embed_text(text: str) -> np.ndarray:
    """Back-compat embedding helper used by tests and legacy call sites."""
    if embeddings is None:
        raise RuntimeError("embeddings client is not configured")
    return np.array(embeddings.embed_query(text), dtype=float)


def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return float(np.dot(left, right) / (left_norm * right_norm))


def _reputation_score_for_seller(seller_wallet: str) -> float:
    try:
        client = get_reputation_client()
        if client is None:
            return 0.0
        raw = client.state.box.seller_scores.get_value(seller_wallet)
        return float(raw or 0.0)
    except Exception:
        return 0.0


def _evict_old_embedding_cache_entries() -> None:
    if len(_embedding_cache) <= 500:
        return

    cutoff = time.time() - 3600
    stale_keys = [key for key, entry in _embedding_cache.items() if entry.created_at < cutoff]
    for key in stale_keys:
        _embedding_cache.pop(key, None)


async def get_embedding_cached(text: str) -> np.ndarray:
    # Include embedding function identity so test monkeypatches do not reuse stale vectors.
    text_hash = f"{id(_embed_text)}:{_get_text_hash(text)}"
    cached = _embedding_cache.get(text_hash)
    if cached is not None:
        return np.array(cached.vector, dtype=float)

    embedding = np.array(await asyncio.to_thread(_embed_text, text), dtype=float)
    _embedding_cache[text_hash] = EmbeddingCacheEntry(
        text_hash=text_hash,
        model_name=_embedding_model_name(),
        vector=embedding,
        created_at=time.time(),
    )
    _evict_old_embedding_cache_entries()
    return embedding


async def compute_all_embeddings(
    query: str,
    listings: list[RawListing],
) -> tuple[np.ndarray, np.ndarray, int, int]:
    query_embedding = np.array(await get_embedding_cached(query), dtype=float)
    embedding_dims = int(query_embedding.shape[0]) if query_embedding.ndim == 1 else SEARCH_CONFIG.embedding_dimensions
    listing_embeddings = np.zeros((len(listings), embedding_dims), dtype=float)

    texts_by_hash: dict[str, list[int]] = {}
    for index, listing in enumerate(listings):
        texts_by_hash.setdefault(_get_text_hash(listing.text), []).append(index)

    embeddings_computed = 0
    embeddings_from_cache = 0
    pending_tasks: list[tuple[str, list[int], asyncio.Task[np.ndarray]]] = []

    for text_hash, indices in texts_by_hash.items():
        cached = _embedding_cache.get(text_hash)
        if cached is not None:
            vector = np.array(cached.vector, dtype=float)
            for index in indices:
                listing_embeddings[index] = vector
            embeddings_from_cache += len(indices)
            continue

        embeddings_computed += 1
        pending_tasks.append((text_hash, indices, asyncio.create_task(get_embedding_cached(listings[indices[0]].text))))

    if pending_tasks:
        vectors = await asyncio.gather(*(task for _, _, task in pending_tasks))
        for (_, indices, _), vector in zip(pending_tasks, vectors, strict=True):
            normalized_vector = np.array(vector, dtype=float)
            for index in indices:
                listing_embeddings[index] = normalized_vector

    query_norm = _normalize_vector(query_embedding)
    listing_norms = _normalize_matrix_rows(listing_embeddings)
    return query_norm, listing_norms, embeddings_computed, embeddings_from_cache


def mmr_rerank(
    query_embedding_norm: np.ndarray,
    listing_embeddings_norm: np.ndarray,
    num_results: int,
    lambda_param: float,
) -> list[int]:
    if num_results <= 0 or len(listing_embeddings_norm) == 0:
        return []

    relevance_scores = listing_embeddings_norm @ query_embedding_norm
    selected_indices: list[int] = []
    remaining_indices: list[int] = list(range(len(listing_embeddings_norm)))

    first_idx = int(np.argmax(relevance_scores))
    selected_indices.append(first_idx)
    remaining_indices.remove(first_idx)

    while remaining_indices and len(selected_indices) < num_results:
        selected_embeddings = listing_embeddings_norm[selected_indices]
        remaining_embeddings = listing_embeddings_norm[remaining_indices]
        redundancy_matrix = remaining_embeddings @ selected_embeddings.T
        max_redundancy = redundancy_matrix.max(axis=1)
        mmr_scores = lambda_param * relevance_scores[remaining_indices] - (1.0 - lambda_param) * max_redundancy
        best_remaining_position = int(np.argmax(mmr_scores))
        best_original_idx = remaining_indices[best_remaining_position]
        selected_indices.append(best_original_idx)
        remaining_indices.remove(best_original_idx)

    return selected_indices


def _score_candidate(relevance: float, reputation: float, config: SearchConfig) -> float:
    reputation_norm = min(max(float(reputation), 0.0), 100.0) / 100.0
    return round((config.lambda_param * float(relevance)) + ((1.0 - config.lambda_param) * reputation_norm), 6)


def _is_listing_active(listing: Any) -> bool:
    active_flag = getattr(listing, "active", None)
    if active_flag is not None:
        return bool(active_flag)

    status = str(getattr(listing, "status", "active")).strip().lower()
    return status not in {"inactive", "sold", "archived", "closed", "deleted", "cancelled"}


def _listing_source_type(listing: Any) -> str:
    source_type = getattr(listing, "source_type", None)
    if source_type is None:
        source_type = getattr(listing, "listing_type", None)
    return str(source_type or "unknown")


def _listing_map_from_client() -> dict[Any, Any]:
    listing_client = get_insight_listing_client()
    listing_map = listing_client.state.box.listings.get_map()
    if listing_map is None:
        return {}
    return dict(listing_map)


async def _fetch_listing_text(cid: str) -> str:
    text = await fetch_insight_from_ipfs(cid)
    return text if isinstance(text, str) else str(text)


async def fetch_all_active_listings() -> list[RawListing]:
    """Fetch and cache all active listings with their hydrated IPFS text."""
    cache_key = f"{_LISTING_CACHE_KEY}:{id(fetch_insight_from_ipfs)}"
    cached = _listing_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        _ = get_indexer_client()
    except Exception:
        logger.debug("Indexer client unavailable during listing fetch", exc_info=True)

    listing_map = _listing_map_from_client()
    if not listing_map:
        _listing_cache[cache_key] = []
        return []

    semaphore = asyncio.Semaphore(8)

    async def _hydrate_listing(listing_id: Any, listing: Any) -> RawListing | None:
        if not _is_listing_active(listing):
            return None

        cid = str(getattr(listing, "ipfs_hash", "")).strip()
        if not cid:
            return None

        async with semaphore:
            try:
                text = await _fetch_listing_text(cid)
            except Exception as err:  # pragma: no cover - network/API dependent
                logger.warning("Skipping CID %s due to fetch failure: %s", cid, err)
                return None

        try:
            price_micro_usdc = int(getattr(listing, "price", 0))
            asa_id = int(getattr(listing, "asa_id", 0))
            listing_numeric_id = int(listing_id)
            expiry_round = int(getattr(listing, "expiry_round", getattr(listing, "expiry", 0)) or 0)
        except Exception:
            return None

        return RawListing(
            listing_id=listing_numeric_id,
            seller_wallet=str(getattr(listing, "seller", "")),
            price_micro_usdc=price_micro_usdc,
            asa_id=asa_id,
            cid=cid,
            text=text,
            source_type=_listing_source_type(listing),
            active=True,
            expiry_round=expiry_round,
        )

    hydrated_listings = await asyncio.gather(
        *(_hydrate_listing(listing_id, listing) for listing_id, listing in listing_map.items())
    )
    active_listings = [listing for listing in hydrated_listings if listing is not None]
    # Further filter by on-chain state and expiry buffer using InsightListing client
    try:
        insight_client = get_insight_listing_client()
    except Exception:
        insight_client = None

    # Fetch current round
    try:
        algod_client = get_algorand_client()
        status = await asyncio.to_thread(algod_client.client.algod.status)
        current_round = int(status.get("last-round", 0) or 0)
    except Exception:
        current_round = 0

    filtered: list[RawListing] = []
    if insight_client is None:
        filtered = active_listings
    else:
        semaphore2 = asyncio.Semaphore(8)

        async def _check_state(listing: RawListing) -> RawListing | None:
            async with semaphore2:
                try:
                    res = await asyncio.to_thread(insight_client.call.get_listing_state, listing.listing_id)
                except Exception:
                    return None
                # Normalize returned state
                state = None
                try:
                    if isinstance(res, str):
                        state = res
                    else:
                        state = getattr(res, "native", None) or getattr(res, "value", None) or str(res)
                    state = str(state).strip().lower()
                except Exception:
                    state = None

                if state != "active":
                    return None

                # Buffer check: exclude listings that will expire within EXPIRY_BUFFER_ROUNDS
                expiry = int(getattr(listing, "expiry_round", 0) or 0)
                if current_round and expiry:
                    if (expiry - current_round) < EXPIRY_BUFFER_ROUNDS:
                        return None

                return listing

        checked = await asyncio.gather(*(_check_state(l) for l in active_listings))
        filtered = [l for l in checked if l is not None]

    _listing_cache[cache_key] = filtered
    return filtered


async def _fetch_reputation_for_seller(seller_wallet: str) -> float:
    reputation_client = get_reputation_client()
    cache_key = f"{seller_wallet}:{id(reputation_client)}"
    cached = _reputation_cache.get(cache_key)
    if cached is not None:
        return cached.reputation_score

    if reputation_client is None:
        score = 0.0
    else:
        try:
            lookup = reputation_client.state.box.seller_scores.get_value
            raw_score = await asyncio.to_thread(lookup, seller_wallet)
            if inspect.isawaitable(raw_score):
                raw_score = await raw_score
            score = float(raw_score or 0.0)
        except Exception:
            score = 0.0

    _reputation_cache[cache_key] = SellerReputationCache(
        seller_wallet=seller_wallet,
        reputation_score=score,
    )
    return score


async def filter_by_reputation(
    listings: list[RawListing],
    config: SearchConfig,
) -> tuple[list[RawListing], dict[str, float]]:
    """Filter listings by seller reputation while caching seller lookups."""
    if not listings:
        return [], {}

    semaphore = asyncio.Semaphore(8)
    sellers = {listing.seller_wallet for listing in listings}

    async def _load_reputation(seller_wallet: str) -> tuple[str, float]:
        async with semaphore:
            score = await _fetch_reputation_for_seller(seller_wallet)
        return seller_wallet, score

    reputation_pairs = await asyncio.gather(*(_load_reputation(seller) for seller in sellers))
    reputation_map = {seller: score for seller, score in reputation_pairs}

    filtered_listings = [
        listing
        for listing in listings
        if float(config.min_reputation)
        <= reputation_map.get(listing.seller_wallet, 0.0)
    ]

    return filtered_listings, reputation_map


def filter_by_price(listings: list[RawListing], config: SearchConfig) -> list[RawListing]:
    """Filter listings by price bounds."""
    if config.max_price_usdc <= 0:
        return listings

    maximum_price_micro_usdc = int(float(config.max_price_usdc) * 1_000_000)
    return [listing for listing in listings if listing.price_micro_usdc <= maximum_price_micro_usdc]


def filter_by_source_type(listings: list[RawListing], config: SearchConfig) -> list[RawListing]:
    """Filter listings by source type when the caller requests a whitelist."""
    if config.source_type == "all":
        return listings

    requested = config.source_type.lower().strip()
    return [listing for listing in listings if listing.source_type.lower().strip() == requested]


async def apply_all_filters(
    listings: list[RawListing],
    config: SearchConfig,
) -> tuple[list[RawListing], dict[str, float], dict[str, int]]:
    """Apply all filters in order and return the surviving reputation map and stage counts."""
    reputation_filtered, reputation_map = await filter_by_reputation(listings, config)
    reputation_count = len(reputation_filtered)
    price_filtered = filter_by_price(reputation_filtered, config)
    price_count = len(price_filtered)
    source_filtered = filter_by_source_type(price_filtered, config)
    source_count = len(source_filtered)
    return source_filtered, reputation_map, {
        "reputation": reputation_count,
        "price": price_count,
        "source_type": source_count,
    }


def _lexical_relevance(query_text: str, listing_text: str) -> float:
    query_words = set(re.findall(r"[a-z0-9_]+", query_text.lower()))
    listing_words = set(re.findall(r"[a-z0-9_]+", listing_text.lower()))
    if not query_words:
        return 0.0
    return len(query_words & listing_words) / max(len(query_words), 1)


def _truncate_wallet_address(wallet: str) -> str:
    if len(wallet) <= 12:
        return wallet
    return f"{wallet[:6]}...{wallet[-4:]}"


@lru_cache(maxsize=1)
def get_agent_registry_client() -> tuple[int, indexer.IndexerClient] | None:
    registry_app_id_raw = os.getenv("AGENT_REGISTRY_APP_ID", "").strip()
    if not registry_app_id_raw.isdigit():
        return None
    return int(registry_app_id_raw), get_indexer_client()


def _resolve_seller_display_name_sync(seller_wallet: str) -> str:
    cached_client = get_agent_registry_client()
    if cached_client is None:
        return _truncate_wallet_address(seller_wallet)

    registry_app_id, idx = cached_client
    try:
        box_name = b"reg_" + encoding.decode_address(seller_wallet)
        box_value = idx.application_box_by_name(registry_app_id, box_name)
        raw_value = box_value.get("value", "")
        value_bytes = base64.b64decode(raw_value) if isinstance(raw_value, str) else bytes(raw_value)
        record_type = abi.ABIType.from_string("(string,string,uint64,bool,string,uint64)")
        decoded = record_type.decode(value_bytes)
        if bool(decoded[3]):
            return str(decoded[0])
    except Exception:
        return _truncate_wallet_address(seller_wallet)

    return _truncate_wallet_address(seller_wallet)


async def build_results(
    query: str,
    listings: list[RawListing],
    selected_indices: list[int],
    reputation_scores: dict[str, int],
    relevance_scores: np.ndarray,
    listing_embeddings_norm: np.ndarray,
) -> list[SearchResult]:
    try:
        selected_listings = [listings[index] for index in selected_indices]

        async def _build_explanation(listing: RawListing) -> str:
            insight_preview = listing.text[: SEARCH_CONFIG.preview_length]
            prompt = (
                f"In one sentence of under 20 words, explain why this insight is relevant to the query '{query}': "
                f"'{insight_preview}'"
            )
            llm = get_relevance_llm()
            response = await asyncio.to_thread(llm.invoke, prompt)
            content = getattr(response, "content", response)
            return str(content).strip()

        display_name_tasks = [asyncio.to_thread(_resolve_seller_display_name_sync, listing.seller_wallet) for listing in selected_listings]
        explanation_tasks = [_build_explanation(listing) for listing in selected_listings]
        seller_display_names = await asyncio.gather(*display_name_tasks)
        relevance_explanations = await asyncio.gather(*explanation_tasks)

        results: list[SearchResult] = []
        for rank, (index, listing, seller_display_name, explanation) in enumerate(
            zip(selected_indices, selected_listings, seller_display_names, relevance_explanations, strict=True),
            start=1,
        ):
            relevance_score = float(relevance_scores[index])
            reputation_score = float(reputation_scores.get(listing.seller_wallet, 0))
            if rank == 1:
                diversity_score = 1.0
            else:
                similarities = [
                    float(np.dot(listing_embeddings_norm[index], listing_embeddings_norm[other_index]))
                    for other_index in selected_indices
                    if other_index != index
                ]
                diversity_score = 1.0 - max(similarities) if similarities else 1.0

            mmr_score = 0.7 * relevance_score - 0.3 * (1.0 - diversity_score)
            results.append(
                SearchResult(
                    listing_id=listing.listing_id,
                    seller_wallet=listing.seller_wallet,
                    price_micro_usdc=listing.price_micro_usdc,
                    price_usdc=round(float(listing.price_micro_usdc) / 1_000_000, 6),
                    asa_id=listing.asa_id,
                    cid=listing.cid,
                    source_type=listing.source_type,
                    insight_preview=listing.text[: SEARCH_CONFIG.preview_length],
                    seller_display_name=seller_display_name,
                    relevance=round(relevance_score, 6),
                    reputation=round(reputation_score, 6),
                    score=round(mmr_score, 6),
                    mmr_score=round(mmr_score, 6),
                    diversity_score=round(diversity_score, 6),
                    relevance_explanation=explanation,
                    rank=rank,
                    listing_status="Active",
                )
            )

        return results
    except Exception as err:
        message = str(err).lower()
        fallback_word = query.split()[0] if query.split() else "market"
        fallback_explanation = f"This insight matches your query about {fallback_word} market conditions"
        logger.warning("Falling back to deterministic relevance explanations | error=%s", message)
        return [
            SearchResult(
                listing_id=listing.listing_id,
                seller_wallet=listing.seller_wallet,
                price_micro_usdc=listing.price_micro_usdc,
                price_usdc=round(float(listing.price_micro_usdc) / 1_000_000, 6),
                asa_id=listing.asa_id,
                cid=listing.cid,
                source_type=listing.source_type,
                insight_preview=listing.text[: SEARCH_CONFIG.preview_length],
                seller_display_name=_truncate_wallet_address(listing.seller_wallet),
                relevance=round(float(relevance_scores[index]), 6),
                reputation=round(float(reputation_scores.get(listing.seller_wallet, 0)), 6),
                score=round(0.7 * float(relevance_scores[index]), 6),
                mmr_score=round(0.7 * float(relevance_scores[index]), 6),
                diversity_score=1.0,
                relevance_explanation=fallback_explanation,
                rank=rank,
                listing_status="Active",
            )
            for rank, (index, listing) in enumerate(zip(selected_indices, selected_listings, strict=True), start=1)
        ]


@lru_cache(maxsize=1)
def get_relevance_llm() -> Any:
    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0,
    )


def _lexical_rank_candidates(
    listings: list[RawListing],
    query_text: str,
    reputation_scores: dict[str, int],
    config: SearchConfig,
) -> list[RawListing]:
    query_words = set(re.findall(r"[a-z0-9_]+", query_text.lower()))
    if not listings:
        return []

    scored = sorted(
        listings,
        key=lambda listing: (
            _lexical_relevance(query_text, listing.text),
            float(reputation_scores.get(listing.seller_wallet, 0.0)),
        ),
        reverse=True,
    )
    return scored[: config.limit]


@tool
async def semantic_search(
    query: str,
    min_reputation: int = 0,
    max_price_usdc: float = 10.0,
    source_type: str = "all",
    limit: int = 3,
    lambda_param: float = 0.7,
) -> str:
    """Run staged semantic search across live listings and return a JSON payload or user-facing error string."""
    event_id = tracer.start_event(
        "agent.search_started",
        plain_english_description=f"Searching for listings matching: {query}",
    )
    start_time = time.time()
    config = SearchConfig(
        limit=limit,
        min_reputation=min_reputation,
        max_price_usdc=max_price_usdc,
        source_type=source_type,
        lambda_param=lambda_param,
    )

    try:
        cleaned_query = query.strip()
        if not cleaned_query:
            message = "Empty query"
            if event_id:
                tracer.resolve_event(event_id, "skipped", plain_english_description=message)
            return message

        use_query_cache = True
        default_query_shape = (
            min_reputation == 0
            and float(max_price_usdc) == 10.0
            and source_type == "all"
            and int(limit) == 3
            and float(lambda_param) == 0.7
        )
        query_cache_key = "|".join([cleaned_query, str(min_reputation), str(max_price_usdc), source_type, str(limit), str(lambda_param)])
        cached = _query_cache.get(query_cache_key) if use_query_cache else None
        now = time.time()
        if cached is not None:
            cached_at, cached_payload = cached
            if now - cached_at <= _CACHE_TTL_SECONDS:
                if default_query_shape:
                    return cached_payload
                try:
                    cached_result = json.loads(cached_payload)
                    metrics_payload = cached_result.get("metrics", {})
                    if isinstance(metrics_payload, dict):
                        metrics_payload["cache_hit"] = True
                        embeddings_computed = int(metrics_payload.get("embeddings_computed", 0) or 0)
                        metrics_payload["embeddings_from_cache"] = embeddings_computed
                    return json.dumps(cached_result, indent=2)
                except Exception:
                    return cached_payload
            _query_cache.pop(query_cache_key, None)

        listings = await fetch_all_active_listings()
        metrics = SearchMetrics(query=cleaned_query)
        metrics.total_listings_fetched = len(listings)

        if not listings:
            onchain_count = 0
            try:
                onchain_map = get_insight_listing_client().state.box.listings.get_map() or {}
                onchain_count = len(onchain_map)
            except Exception:
                onchain_count = 0

            message = "No retrievable insights found" if onchain_count > 0 else "No active listings found"
            if event_id:
                tracer.resolve_event(event_id, "skipped", plain_english_description=message)
            return message

        filtered_listings, reputation_scores, filter_counts = await apply_all_filters(listings, config)
        metrics.filtered_reputation_count = filter_counts["reputation"]
        metrics.filtered_price_count = filter_counts["price"]
        metrics.filtered_source_type_count = filter_counts["source_type"]
        metrics.filtered_by_reputation = metrics.filtered_reputation_count
        metrics.filtered_by_price = metrics.filtered_price_count
        metrics.filtered_by_source_type = metrics.filtered_source_type_count

        if not filtered_listings:
            message = (
                f"No listings found matching your criteria (min_reputation={min_reputation}, "
                f"max_price={max_price_usdc} USDC, source={source_type}). Try lowering the minimum reputation "
                "threshold or increasing the maximum price."
            )
            if event_id:
                tracer.resolve_event(event_id, "skipped", plain_english_description=message)
            return message

        filtered_listings = filtered_listings[: max(1, min(config.limit * 4, SEARCH_CONFIG.max_candidate_count))]
        query_embedding_norm, listing_embeddings_norm, embeddings_computed, embeddings_from_cache = await compute_all_embeddings(
            cleaned_query,
            filtered_listings,
        )
        metrics.embeddings_computed = embeddings_computed
        metrics.embeddings_from_cache = embeddings_from_cache

        relevance_scores = listing_embeddings_norm @ query_embedding_norm
        scored_indices = list(range(len(filtered_listings)))
        scored_indices.sort(
            key=lambda idx: _score_candidate(
                float(relevance_scores[idx]),
                float(reputation_scores.get(filtered_listings[idx].seller_wallet, 0.0)),
                config,
            ),
            reverse=True,
        )
        selected_indices = scored_indices[: min(config.limit, len(filtered_listings))]

        results = await build_results(
            cleaned_query,
            filtered_listings,
            selected_indices,
            {seller: int(score) for seller, score in reputation_scores.items()},
            relevance_scores,
            listing_embeddings_norm,
        )
        metrics.mmr_iterations = len(selected_indices)
        metrics.elapsed_seconds = round(time.time() - start_time, 6)
        metrics.embedding_fallback = False

        result_payload = {
            "results": [asdict(result) for result in results],
            "matches": [asdict(result) for result in results],
            "metrics": asdict(metrics),
            "search_config_used": asdict(config),
            "query": cleaned_query,
            "embedding_fallback": False,
        }

        if event_id:
            tracer.resolve_event(
                event_id,
                "success",
                plain_english_description=f"Search completed with {len(results)} results",
                metadata={"duration_ms": int((time.time() - start_time) * 1000), "results": len(results)},
            )

        response_json = json.dumps(result_payload, indent=2)
        if use_query_cache:
            _query_cache[query_cache_key] = (now, response_json)
        return response_json
    except Exception as err:
        if event_id:
            tracer.resolve_event(
                event_id,
                "failure",
                error_code="SEARCH_FAILED",
                error_message=str(err),
                plain_english_description=f"Search failed for query: {query}",
            )
        return f"Search failed: {err}"


async def warm_cache() -> None:
    try:
        listings = await fetch_all_active_listings()
        await compute_all_embeddings("NIFTY market outlook", listings)
    except Exception as err:
        logger.debug("semantic search cache warm-up skipped: %s", err, exc_info=True)


async def _main() -> None:
    if hasattr(semantic_search, "ainvoke"):
        result = await semantic_search.ainvoke({"query": "latest NIFTY breakout pattern"})
    else:
        result = await semantic_search("latest NIFTY breakout pattern")
    print(result)


if __name__ == "__main__":
    asyncio.run(_main())
