"""Semantic search tool scaffolding for the Mercator buyer agent."""

from __future__ import annotations

import os
from functools import lru_cache

import numpy as np
from algosdk.v2client import indexer
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from tenacity import retry, stop_after_attempt, wait_fixed

from contracts.insight_listing import InsightListingClient
from contracts.reputation import ReputationClient

try:
    from utils.ipfs import upload_insight_to_ipfs
except ImportError:  # pragma: no cover - supports running from repo root
    from backend.utils.ipfs import upload_insight_to_ipfs


load_dotenv()


embeddings = GoogleGenerativeAIEmbeddings(
    model="embedding-004",
    google_api_key=os.getenv("GEMINI_API_KEY"),
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
    return indexer.IndexerClient(token=token, indexer_address=idx_url)


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def embed_text(text: str) -> np.ndarray:
    """Embed text with Gemini embeddings and return a numpy vector."""
    vector = embeddings.embed_query(text)
    return np.array(vector, dtype=float)


@tool
def semantic_search(query: str) -> str:
    """Placeholder semantic search tool for agent wiring.

    Real listing retrieval and ranking will be added in later phases.
    """
    _ = InsightListingClient
    _ = ReputationClient
    _ = upload_insight_to_ipfs
    _ = get_indexer_client()
    _ = embed_text(query)
    return "Semantic search tool initialized. Real on-chain ranking logic pending."
