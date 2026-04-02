"""Post-payment flow for confirmation, escrow release, and content retrieval."""

from __future__ import annotations

from langchain_core.tools import tool
from algosdk.v2client import indexer
from contracts.escrow import EscrowClient
from dotenv import load_dotenv
import os
import asyncio
import time
import logging
from functools import lru_cache
from algokit_utils import AlgorandClient

try:
    from utils.ipfs import fetch_insight_from_ipfs
except ImportError:  # pragma: no cover - supports project-root execution
    from backend.utils.ipfs import fetch_insight_from_ipfs


load_dotenv()

logger = logging.getLogger(__name__)

INDEXER_URL = os.getenv("INDEXER_URL") or os.getenv("INDEXER_SERVER", "")
INDEXER_TOKEN = os.getenv("INDEXER_TOKEN") or os.getenv("ALGOD_TOKEN", "")
ESCROW_APP_ID = int(os.getenv("ESCROW_APP_ID", "0"))
BUYER_WALLET = os.getenv("BUYER_WALLET", "")

if not INDEXER_URL:
    raise ValueError("INDEXER_URL or INDEXER_SERVER not found in environment")
if ESCROW_APP_ID <= 0:
    raise ValueError("ESCROW_APP_ID not found or invalid in environment")

indexer_client = indexer.IndexerClient(INDEXER_TOKEN, INDEXER_URL)


@lru_cache(maxsize=1)
def get_escrow_client() -> EscrowClient:
    """Return a cached Escrow client configured from environment."""
    algorand = AlgorandClient.from_environment()
    deployer_mnemonic = os.getenv("DEPLOYER_MNEMONIC", "").strip()
    deployer_address = os.getenv("DEPLOYER_ADDRESS", "").strip()
    if deployer_mnemonic and deployer_address:
        signer = algorand.account.from_mnemonic(
            mnemonic=deployer_mnemonic,
            sender=deployer_address,
        )
        algorand.set_default_signer(signer)
    return EscrowClient(algorand=algorand, app_id=ESCROW_APP_ID)


escrow_client = get_escrow_client()


async def complete_purchase_flow(tx_id: str, listing_id: int, buyer_wallet: str) -> str:
    """Confirm payment tx, then continue post-payment flow hooks.

    This currently performs robust confirmation polling and returns a status payload.
    Escrow release and content delivery hooks are intentionally staged for next steps.
    """
    if not tx_id.strip():
        raise ValueError("tx_id is required")
    if listing_id < 0:
        raise ValueError("listing_id must be non-negative")
    if not buyer_wallet.strip():
        buyer_wallet = BUYER_WALLET
    if not buyer_wallet.strip():
        raise ValueError("buyer_wallet is required")

    start = time.time()
    timeout_seconds = 30
    poll_interval = 2

    logger.info(
        "Starting post-payment confirmation polling | tx_id=%s listing_id=%s buyer=%s",
        tx_id,
        listing_id,
        buyer_wallet,
    )

    confirmed_round = None
    while time.time() - start < timeout_seconds:
        try:
            tx_info = indexer_client.lookup_transaction(tx_id).transaction()
            confirmed_round = tx_info.get("confirmed-round")
            if confirmed_round:
                logger.info(
                    "Payment confirmed | tx_id=%s round=%s",
                    tx_id,
                    confirmed_round,
                )
                break
        except Exception as exc:
            logger.warning("Indexer lookup retry | tx_id=%s error=%s", tx_id, exc)

        await asyncio.sleep(poll_interval)

    if not confirmed_round:
        raise RuntimeError(
            "Payment was not confirmed within 30 seconds; purchase flow aborted"
        )

    result = {
        "success": True,
        "tx_id": tx_id,
        "listing_id": listing_id,
        "buyer_wallet": buyer_wallet,
        "confirmed_round": confirmed_round,
        "status": "payment_confirmed",
        "next": "escrow_release_and_content_delivery",
    }
    return str(result)


@tool
async def complete_purchase_flow_tool(tx_id: str, listing_id: int, buyer_wallet: str) -> str:
    """LangChain tool wrapper for post-payment confirmation flow."""
    return await complete_purchase_flow(tx_id=tx_id, listing_id=listing_id, buyer_wallet=buyer_wallet)
