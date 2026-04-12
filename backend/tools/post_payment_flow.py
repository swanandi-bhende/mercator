"""Post-payment flow for confirmation, escrow release, and content retrieval.

Purpose: Completes x402 payment flow after on-chain settlement:
1. Poll indexer for payment tx confirmation (up to 30 seconds).
2. Fetch listing details from InsightListing contract (seller, IPFS CID).
3. Fetch insight content from IPFS (with gateway fallback).
4. Call Escrow contract release_after_payment() to unlock seller funds (atomic).
5. Return formatted confirmation message with full insight text + tx links.

Key Behaviors:
- Polling: Waits for indexer to reflect payment tx (handles latency).
- Escrow release: Retried 3 times if stale-round or brief unavailability.
- Content fetch: Parallel with escrow release for speed; IPFS timeout = fallback message.
- Fallback: If escrow fails, still delivers insight (payment confirmed, escrow will settle).

This tool is called automatically by agent after x402 payment succeeds.
Returns: formatted message with insight text + transaction IDs + explorer URLs.
"""

from __future__ import annotations

from langchain_core.tools import tool
from algosdk.v2client import indexer
from algosdk.error import AlgodHTTPError
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
from backend.utils.error_handler import contract_error, ipfs_down

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

# Module-level clients are kept for test monkeypatch compatibility.
escrow_client: EscrowClient | None = None
listing_client: InsightListingClient | None = None


def get_escrow_client() -> EscrowClient:
    """Create escrow client used for release_after_payment calls.

    Input: none (reads escrow app/signer env).
    Output: EscrowClient instance.
    Micropayment role: unlock-record write stage after payment confirmation.
    """
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


def get_listing_client() -> InsightListingClient:
    """Create listing client used to resolve purchased listing metadata.

    Input: none.
    Output: InsightListingClient instance.
    Micropayment role: maps listing id to CID before content delivery.
    """
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

async def _wait_for_confirmation(tx_id: str, timeout_seconds: int = 30) -> int:
    """Poll indexer until transaction is confirmed.

    Inputs: tx_id and timeout_seconds.
    Output: confirmed round number.
    Micropayment role: synchronization barrier before escrow release/content delivery.
    """
    start = time.time()
    while time.time() - start < timeout_seconds:
        try:
            tx_info = indexer_client.transaction(tx_id).get("transaction", {})
            confirmed_round = tx_info.get("confirmed-round")
            if confirmed_round:
                return int(confirmed_round)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Indexer lookup retry | tx_id=%s error=%s", tx_id, exc)
        await asyncio.sleep(0.5)
    raise RuntimeError(
        f"Transaction {tx_id} was not confirmed within {timeout_seconds} seconds"
    )


def _extract_tx_id(result: object) -> str:
    """Extract tx id from various algokit send result shapes.

    Input: send result object.
    Output: transaction id string.
    Micropayment role: tracks escrow release tx for response and confirmation polling.
    """
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
    """Complete post-payment fulfillment and return buyer-facing content message.

    Inputs: payment tx id, listing id, buyer wallet.
    Output: formatted string with confirmation + insight body + tx references.
    Micropayment role: terminal stage of commerce flow after x402 transfer succeeds.
    """
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

    try:
        payment_round = await _wait_for_confirmation(tx_id=tx_id, timeout_seconds=30)
    except Exception as exc:  # noqa: BLE001
        logger.error("Payment confirmation failed | tx_id=%s error=%s", tx_id, exc, exc_info=True)
        raise

    logger.info("Payment confirmed | tx_id=%s round=%s", tx_id, payment_round)

    active_listing_client = listing_client or get_listing_client()
    try:
        listing = active_listing_client.state.box.listings.get_value(listing_id)
    except AlgodHTTPError as exc:
        logger.error("Contract error while reading listing | listing_id=%s error=%s", listing_id, exc)
        return contract_error(logger, str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected contract read error | listing_id=%s error=%s", listing_id, exc)
        return contract_error(logger, str(exc))

    if listing is None:
        raise RuntimeError(f"Listing {listing_id} not found in InsightListing state")

    cid = str(listing.ipfs_hash)

    async def _release_escrow_with_retry() -> tuple[str, int | None]:
        """Try escrow release a few times to avoid stale round failures."""
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                active_escrow_client = escrow_client or get_escrow_client()
                redeem_result = active_escrow_client.send.release_after_payment((buyer_wallet, listing_id))
                tx = _extract_tx_id(redeem_result)
                round_no = await _wait_for_confirmation(tx_id=tx, timeout_seconds=20)
                return tx, round_no
            except AlgodHTTPError as exc:
                last_error = exc
                logger.error(
                    "Contract error during escrow release | attempt=%s listing_id=%s error=%s",
                    attempt,
                    listing_id,
                    exc,
                )
                await asyncio.sleep(0.4)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "Escrow redeem attempt failed | attempt=%s listing_id=%s error=%s",
                    attempt,
                    listing_id,
                    exc,
                )
                await asyncio.sleep(0.4)
        raise RuntimeError(f"Escrow redeem failed after retries: {last_error}")

    escrow_task = asyncio.create_task(_release_escrow_with_retry())
    ipfs_task = asyncio.create_task(fetch_insight_from_ipfs(cid))

    try:
        insight_text = await ipfs_task
        demo_logger.info("IPFS content delivered")
    except Exception as exc:  # noqa: BLE001
        logger.warning("IPFS fetch failed after payment confirmation | cid=%s error=%s", cid, exc)
        insight_text = ipfs_down(logger, str(exc))

    escrow_tx_id = ""
    escrow_round = None
    try:
        escrow_tx_id, escrow_round = await escrow_task
        logger.info("Escrow redeem confirmed | tx_id=%s round=%s", escrow_tx_id, escrow_round)
        demo_logger.info("Escrow released")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Escrow redeem unavailable; continuing with paid content delivery | error=%s", exc)
        escrow_hint = "Escrow release skipped. Your payment is confirmed; please retry in a few seconds."
        if insight_text.startswith("IPFS downtime"):
            return f"{escrow_hint}\nInsight content could not be retrieved: {insight_text}"
        return (
            "✅ Payment confirmed!\n"
            f"⚠ {escrow_hint}\n\n"
            "Here is your human trading insight:\n\n"
            f"{insight_text}\n\n"
            f"Transaction IDs: payment={tx_id}"
        )

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
    """LangChain tool wrapper around complete_purchase_flow.

    Inputs: tx_id, listing_id, buyer_wallet.
    Output: same formatted fulfillment string as complete_purchase_flow.
    Micropayment role: agent-callable bridge from payment tool to delivery stage.
    """
    return await complete_purchase_flow(tx_id=tx_id, listing_id=listing_id, buyer_wallet=buyer_wallet)
