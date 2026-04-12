"""Manual integration utility for IPFS + listing contract path.

Purpose: Smoke-test seller publish flow by uploading sample text to Pinata,
optionally funding listing app account, and storing CID via InsightListing contract.
"""

from __future__ import annotations

import asyncio
import base64
import os
from pathlib import Path

from algosdk import mnemonic
from algosdk.logic import get_application_address
from algosdk.transaction import PaymentTxn, wait_for_confirmation
from algosdk.v2client import algod
from algosdk.v2client import indexer
from dotenv import load_dotenv

from backend.utils.ipfs import store_cid_in_listing, upload_insight_to_ipfs


def _get_indexer_client() -> indexer.IndexerClient:
    """Create indexer client for transaction search operations.

    Input: none (reads INDEXER_URL/INDEXER_SERVER and token env vars).
    Output: configured IndexerClient.
    Micropayment role: verifies listing tx existence after CID-to-contract write.
    """
    indexer_url = (
        os.getenv("INDEXER_URL", "").strip()
        or os.getenv("INDEXER_SERVER", "").strip()
    )
    if not indexer_url:
        raise RuntimeError("INDEXER_URL or INDEXER_SERVER must be set")

    token = os.getenv("INDEXER_TOKEN", "").strip() or os.getenv("ALGOD_TOKEN", "").strip()
    return indexer.IndexerClient(indexer_token=token, indexer_address=indexer_url)


def _get_algod_client() -> algod.AlgodClient:
    """Create algod client for account and transaction operations.

    Input: none (reads ALGOD_URL/ALGOD_SERVER and ALGOD_TOKEN).
    Output: configured AlgodClient.
    Micropayment role: funds listing app account before storing listings.
    """
    algod_url = os.getenv("ALGOD_URL", "").strip() or os.getenv("ALGOD_SERVER", "").strip()
    if not algod_url:
        raise RuntimeError("ALGOD_URL or ALGOD_SERVER must be set")

    token = os.getenv("ALGOD_TOKEN", "").strip()
    return algod.AlgodClient(algod_token=token, algod_address=algod_url)


def _ensure_listing_app_funded(app_id: int) -> None:
    """Top up listing app account to satisfy min balance + box storage headroom.

    Input: app_id for InsightListing application.
    Output: none (submits payment tx only when top-up required).
    Micropayment role: avoids on-chain write failures during create_listing calls.
    """
    client = _get_algod_client()
    app_address = get_application_address(app_id)
    app_info = client.account_info(app_address)

    min_balance = int(app_info.get("min-balance", 0))
    balance = int(app_info.get("amount", 0))
    target_balance = min_balance + 300_000

    if balance >= target_balance:
        return

    top_up = target_balance - balance
    deployer_mnemonic = os.getenv("DEPLOYER_MNEMONIC", "").strip()
    if not deployer_mnemonic:
        raise RuntimeError("DEPLOYER_MNEMONIC missing in .env.testnet")

    private_key = mnemonic.to_private_key(deployer_mnemonic)
    sender = os.getenv("DEPLOYER_ADDRESS", "").strip()
    if not sender:
        sender = mnemonic.to_public_key(deployer_mnemonic)

    params = client.suggested_params()
    pay_txn = PaymentTxn(
        sender=sender,
        sp=params,
        receiver=app_address,
        amt=top_up,
    )
    signed = pay_txn.sign(private_key)
    tx_id = client.send_transaction(signed)
    wait_for_confirmation(client, tx_id, 4)
    print(f"APP_TOP_UP_TX_ID={tx_id}")


def _find_cid_tx_id(app_id: int, sender: str, cid: str) -> str | None:
    """Locate application call tx id that includes a target CID in app args.

    Inputs: app_id, sender wallet, and target CID.
    Output: matching tx id or None.
    Micropayment role: maps off-chain CID upload to on-chain listing confirmation evidence.
    """
    idx = _get_indexer_client()
    response = idx.search_transactions(
        application_id=app_id,
        address=sender,
        txn_type="appl",
        limit=30,
    )

    txns = response.get("transactions", [])
    for txn in txns:
        app = txn.get("application-transaction", {})
        app_args = app.get("application-args", [])
        for encoded in app_args:
            try:
                decoded = base64.b64decode(encoded).decode("utf-8", errors="ignore")
            except Exception:
                continue
            if cid in decoded:
                return txn.get("id")
    return None


async def main() -> None:
    """Run manual smoke test: upload sample text, store listing on-chain, print artifacts.

    Input: none (reads env config and uses hardcoded sample insight text).
    Output: console prints for CID, listing id, ASA id, tx id, and explorer links.
    Micropayment role: operator validation of seller-side publish path before live demos.
    """
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env.testnet", override=True)

    listing_app_id = int(os.getenv("INSIGHT_LISTING_APP_ID", "0"))
    seller_address = os.getenv("DEPLOYER_ADDRESS", "").strip()

    if not listing_app_id:
        raise RuntimeError("INSIGHT_LISTING_APP_ID is missing in .env.testnet")
    if not seller_address:
        raise RuntimeError("DEPLOYER_ADDRESS is missing in .env.testnet")

    sample_text = "Sample trading insight: Buy NIFTY above 24500..."
    cid = await upload_insight_to_ipfs(sample_text)
    print(f"CID={cid}")

    _ensure_listing_app_funded(listing_app_id)

    listing_id, asa_id = store_cid_in_listing(
        cid=cid,
        listing_app_id=listing_app_id,
        seller_address=seller_address,
    )
    print(f"LISTING_ID={listing_id}")
    print(f"ASA_ID={asa_id}")

    tx_id = _find_cid_tx_id(listing_app_id, seller_address, cid)
    if tx_id:
        print(f"TX_ID={tx_id}")
        print(f"EXPLORER_TX=https://testnet.algoexplorer.io/tx/{tx_id}")
    else:
        print("TX_ID=NOT_FOUND")
        print("EXPLORER_TX=NOT_FOUND")

    print(f"IPFS_GATEWAY=https://gateway.pinata.cloud/ipfs/{cid}")
    print(f"EXPLORER_ASSET=https://testnet.algoexplorer.io/asset/{asa_id}")


if __name__ == "__main__":
    asyncio.run(main())
