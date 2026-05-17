"""Async wrappers around synchronous py-algorand-sdk client calls.

These wrappers use `asyncio.to_thread` to run blocking SDK calls without
blocking the event loop. Each function accepts an optional client instance;
if omitted, a new client is created from environment via helper in
`backend.main`.
"""
from __future__ import annotations

import asyncio
from typing import Any


async def algod_status(algod_client: Any | None = None) -> dict:
    if algod_client is None:
        from backend.main import _get_algod_client

        algod_client = _get_algod_client()
    return await asyncio.to_thread(algod_client.status)


async def algod_application_info(app_id: int, algod_client: Any | None = None) -> dict:
    if algod_client is None:
        from backend.main import _get_algod_client

        algod_client = _get_algod_client()
    return await asyncio.to_thread(algod_client.application_info, app_id)


async def algod_suggested_params(algod_client: Any | None = None) -> Any:
    if algod_client is None:
        from backend.main import _get_algod_client

        algod_client = _get_algod_client()
    return await asyncio.to_thread(algod_client.suggested_params)


async def algod_account_info(address: str, algod_client: Any | None = None) -> dict:
    if algod_client is None:
        from backend.main import _get_algod_client

        algod_client = _get_algod_client()
    return await asyncio.to_thread(algod_client.account_info, address)


async def indexer_account_transactions(address: str, indexer_client: Any | None = None, **kwargs) -> dict:
    if indexer_client is None:
        from backend.main import _get_indexer_client

        indexer_client = _get_indexer_client()
    return await asyncio.to_thread(indexer_client.account_transactions, address, **kwargs)


async def indexer_search_assets(creator: str, limit: int = 200, indexer_client: Any | None = None) -> dict:
    if indexer_client is None:
        from backend.main import _get_indexer_client

        indexer_client = _get_indexer_client()
    return await asyncio.to_thread(indexer_client.search_assets, creator=creator, limit=limit)


async def algod_send_raw_transaction(signed_txn: Any, algod_client: Any | None = None) -> str:
    if algod_client is None:
        from backend.main import _get_algod_client

        algod_client = _get_algod_client()
    return await asyncio.to_thread(algod_client.send_raw_transaction, signed_txn)


async def algod_pending_transaction_info(tx_id: str, algod_client: Any | None = None) -> dict:
    if algod_client is None:
        from backend.main import _get_algod_client

        algod_client = _get_algod_client()
    return await asyncio.to_thread(algod_client.pending_transaction_info, tx_id)
