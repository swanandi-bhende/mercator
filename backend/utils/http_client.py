"""Shared httpx AsyncClient singleton for the application.

Usage:
  await startup_http_client()  # create the client at app startup
  client = await get_http_client()  # use in request handlers and utilities
  await shutdown_http_client()  # close at app shutdown
"""
from __future__ import annotations

import httpx
from typing import Optional

_shared_client: Optional[httpx.AsyncClient] = None


async def get_http_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None:
        raise RuntimeError("HTTP client not initialised — call startup_http_client() first")
    return _shared_client


async def startup_http_client() -> None:
    global _shared_client
    if _shared_client is not None:
        return
    limits = httpx.Limits(max_connections=10, max_keepalive_connections=5, keepalive_expiry=30.0)
    timeout = httpx.Timeout(connect=2.0, read=5.0, write=2.0, pool=1.0)
    _shared_client = httpx.AsyncClient(limits=limits, timeout=timeout, headers={"User-Agent": "Mercator/1.0 AlgoBharat-Round3"})


async def shutdown_http_client() -> None:
    global _shared_client
    if _shared_client is not None:
        try:
            await _shared_client.aclose()
        finally:
            _shared_client = None
