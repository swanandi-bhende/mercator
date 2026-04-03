"""Post-payment flow for confirmation, escrow release, and content retrieval."""

from __future__ import annotations

from langchain_core.tools import tool
from algosdk.v2client import indexer
from contracts.escrow import EscrowClient
from contracts.insight_listing import InsightListingClient
from dotenv import load_dotenv
import os
import asyncio
import time
import logging
from functools import lru_cache
from algokit_utils import AlgorandClient
from backend.utils.runtime_env import configure_demo_logging, normalize_network_env

try:
    from utils.ipfs import fetch_insight_from_ipfs
except ImportError:  # pragma: no cover - supports project-root execution
    from backend.utils.ipfs import fetch_insight_from_ipfs


normalize_network_env()
demo_logger = configure_demo_logging()

logger = logging.getLogger(__name__)

INDEXER_URL = os.getenv("INDEXER_URL") or os.getenv("INDEXER_SERVER", "")
INDEXER_TOKEN = os.getenv("INDEXER_TOKEN") or os.getenv("ALGOD_TOKEN", "")
ESCROW_APP_ID = int(os.getenv("ESCROW_APP_ID", "0"))
INSIGHT_LISTING_APP_ID = int(os.getenv("INSIGHT_LISTING_APP_ID", "0"))
BUYER_WALLET = os.getenv("BUYER_WALLET", "")
BUYER_MNEMONIC = os.getenv("BUYER_MNEMONIC", "")

if not INDEXER_URL:
    raise ValueError("INDEXER_URL or INDEXER_SERVER not found in environment")
if ESCROW_APP_ID <= 0:
    raise ValueError("ESCROW_APP_ID not found or invalid in environment")
if INSIGHT_LISTING_APP_ID <= 0:
    raise ValueError("INSIGHT_LISTING_APP_ID not found or invalid in environment")

indexer_client = indexer.IndexerClient(INDEXER_TOKEN, INDEXER_URL)


@lru_cache(maxsize=1)
def get_escrow_client() -> EscrowClient:
    """Return a cached Escrow client configured from environment."""
    normalize_network_env()
    algorand = AlgorandClient.from_environment()
    signer_mnemonic = BUYER_MNEMONIC.strip() or os.getenv("DEPLOYER_MNEMONIC", "").strip()
    signer_address = BUYER_WALLET.strip() or os.getenv("DEPLOYER_ADDRESS", "").strip()
    if signer_mnemonic and signer_address:
        signer = algorand.account.from_mnemonic(
            mnemonic=signer_mnemonic,
            sender=signer_address,
        )
        algorand.set_default_signer(signer)
        return EscrowClient(
            algorand=algorand,
            app_id=ESCROW_APP_ID,
            default_sender=signer_address,
        )
    return EscrowClient(algorand=algorand, app_id=ESCROW_APP_ID)


@lru_cache(maxsize=1)
def get_listing_client() -> InsightListingClient:
    """Return a cached InsightListing client configured from environment."""
    normalize_network_env()
    algorand = AlgorandClient.from_environment()
    signer_mnemonic = BUYER_MNEMONIC.strip() or os.getenv("DEPLOYER_MNEMONIC", "").strip()
    signer_address = BUYER_WALLET.strip() or os.getenv("DEPLOYER_ADDRESS", "").strip()
    if signer_mnemonic and signer_address:
        signer = algorand.account.from_mnemonic(
            mnemonic=signer_mnemonic,
            sender=signer_address,
        )
        algorand.set_default_signer(signer)
        return InsightListingClient(
            algorand=algorand,
            app_id=INSIGHT_LISTING_APP_ID,
            default_sender=signer_address,
        )
    return InsightListingClient(algorand=algorand, app_id=INSIGHT_LISTING_APP_ID)


escrow_client = get_escrow_client()
listing_client = get_listing_client()


async def _wait_for_confirmation(tx_id: str, timeout_seconds: int = 30) -> int:
    """Poll indexer for transaction confirmation and return confirmed round."""
    start = time.time()
    while time.time() - start < timeout_seconds:
        try:
            tx_info = indexer_client.transaction(tx_id).get("transaction", {})
            confirmed_round = tx_info.get("confirmed-round")
            if confirmed_round:
                return int(confirmed_round)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Indexer lookup retry | tx_id=%s error=%s", tx_id, exc)
        await asyncio.sleep(2)
    raise RuntimeError(
        f"Transaction {tx_id} was not confirmed within {timeout_seconds} seconds"
    )


def _extract_tx_id(result: object) -> str:
    """Extract tx id from algokit send result using resilient fallbacks."""
    tx_id = getattr(result, "tx_id", None)
    if tx_id:
        return str(tx_id)
    tx_ids = getattr(result, "tx_ids", None)
    if tx_ids and isinstance(tx_ids, list) and tx_ids:
        return str(tx_ids[0])
    transaction_obj = getattr(result, "transaction", None)
    if transaction_obj and getattr(transaction_obj, "get_txid", None):
        return str(transaction_obj.get_txid())
    raise RuntimeError("Could not determine escrow transaction id from send result")


async def complete_purchase_flow(tx_id: str, listing_id: int, buyer_wallet: str) -> str:
    """Confirm payment, release escrow, fetch insight content, and return final output."""
    if not tx_id.strip():
        raise ValueError("tx_id is required")
    if listing_id < 0:
        raise ValueError("listing_id must be non-negative")
    if not buyer_wallet.strip():
        buyer_wallet = BUYER_WALLET
    if not buyer_wallet.strip():
        raise ValueError("buyer_wallet is required")

    logger.info(
        "Starting post-payment confirmation polling | tx_id=%s listing_id=%s buyer=%s",
        tx_id,
        listing_id,
        buyer_wallet,
    )

    payment_round = await _wait_for_confirmation(tx_id=tx_id, timeout_seconds=30)
    logger.info("Payment confirmed | tx_id=%s round=%s", tx_id, payment_round)

    # Trigger escrow redeem after payment confirmation when the deployed contract
    # supports the standalone call path. If the on-chain guard requires an atomic
    # group, continue with payment-confirmed content delivery instead of failing.
    escrow_tx_id = ""
    escrow_round = None
    try:
        redeem_result = escrow_client.send.release_after_payment((buyer_wallet, listing_id))
        escrow_tx_id = _extract_tx_id(redeem_result)
        escrow_round = await _wait_for_confirmation(tx_id=escrow_tx_id, timeout_seconds=30)
        logger.info("Escrow redeem confirmed | tx_id=%s round=%s", escrow_tx_id, escrow_round)
        demo_logger.info("Escrow released")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Escrow redeem unavailable; continuing with paid content delivery | error=%s", exc)

    listing = listing_client.state.box.listings.get_value(listing_id)
    if listing is None:
        raise RuntimeError(f"Listing {listing_id} not found in InsightListing state")

    cid = str(listing.ipfs_hash)
    try:
        insight_text = await fetch_insight_from_ipfs(cid)
        demo_logger.info("IPFS content delivered")
    except Exception as exc:  # noqa: BLE001
        logger.warning("IPFS fetch failed after escrow release | cid=%s error=%s", cid, exc)
        insight_text = "Insight content could not be retrieved right now. Please retry shortly."

    escrow_line = f"Transaction IDs: payment={tx_id}"
    if escrow_tx_id:
        escrow_line += f" | escrow={escrow_tx_id}"

    message_parts = [
        "✅ Payment confirmed!",
        "✅ Escrow released!" if escrow_tx_id else "⚠ Escrow release skipped by deployed contract guard.",
        "",
        "Here is your human trading insight:",
        "",
        insight_text,
        "",
        escrow_line,
    ]
    return "\n".join(message_parts)


@tool
async def complete_purchase_flow_tool(tx_id: str, listing_id: int, buyer_wallet: str) -> str:
    """LangChain tool wrapper for post-payment confirmation flow."""
    return await complete_purchase_flow(tx_id=tx_id, listing_id=listing_id, buyer_wallet=buyer_wallet)
