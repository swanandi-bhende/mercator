"""FastAPI backend entrypoint for listing insights."""

from __future__ import annotations

import os
import base64

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from algosdk import mnemonic
from algosdk.logic import get_application_address
from algosdk.transaction import PaymentTxn, wait_for_confirmation
from algosdk.v2client import algod, indexer

try:
    from utils.ipfs import ListingStoreError, upload_insight_to_ipfs, store_cid_in_listing
except ModuleNotFoundError:
    from backend.utils.ipfs import (
        ListingStoreError,
        upload_insight_to_ipfs,
        store_cid_in_listing,
    )


load_dotenv()
load_dotenv(".env.testnet", override=True)

app = FastAPI(title="Mercator Backend")


class ListInsightRequest(BaseModel):
    insight_text: str = Field(min_length=1)
    price: str
    seller_wallet: str = Field(min_length=1)


def _get_algod_client() -> algod.AlgodClient:
    algod_url = os.getenv("ALGOD_URL", "").strip() or os.getenv("ALGOD_SERVER", "").strip()
    if not algod_url:
        raise HTTPException(status_code=500, detail="ALGOD_URL/ALGOD_SERVER is not configured")
    token = os.getenv("ALGOD_TOKEN", "").strip()
    return algod.AlgodClient(algod_token=token, algod_address=algod_url)


def _get_indexer_client() -> indexer.IndexerClient:
    indexer_url = os.getenv("INDEXER_URL", "").strip() or os.getenv("INDEXER_SERVER", "").strip()
    if not indexer_url:
        raise HTTPException(status_code=500, detail="INDEXER_URL/INDEXER_SERVER is not configured")
    token = os.getenv("INDEXER_TOKEN", "").strip() or os.getenv("ALGOD_TOKEN", "").strip()
    return indexer.IndexerClient(indexer_token=token, indexer_address=indexer_url)


def _ensure_listing_app_funded(app_id: int) -> None:
    client = _get_algod_client()
    app_address = get_application_address(app_id)
    app_info = client.account_info(app_address)

    min_balance = int(app_info.get("min-balance", 0))
    balance = int(app_info.get("amount", 0))
    target_balance = min_balance + 300_000
    if balance >= target_balance:
        return

    deployer_mnemonic = os.getenv("DEPLOYER_MNEMONIC", "").strip()
    if not deployer_mnemonic:
        raise HTTPException(status_code=500, detail="DEPLOYER_MNEMONIC is not configured")

    sender = os.getenv("DEPLOYER_ADDRESS", "").strip() or mnemonic.to_public_key(deployer_mnemonic)
    private_key = mnemonic.to_private_key(deployer_mnemonic)

    top_up = target_balance - balance
    params = client.suggested_params()
    pay_txn = PaymentTxn(sender=sender, sp=params, receiver=app_address, amt=top_up)
    tx_id = client.send_transaction(pay_txn.sign(private_key))
    wait_for_confirmation(client, tx_id, 4)


def _find_cid_tx_id(app_id: int, sender: str, cid: str) -> str | None:
    idx = _get_indexer_client()
    response = idx.search_transactions(
        application_id=app_id,
        address=sender,
        txn_type="appl",
        limit=30,
    )

    for txn in response.get("transactions", []):
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/list")
async def list_insight(payload: ListInsightRequest) -> dict[str, int | str]:
    listing_app_id_raw = os.getenv("INSIGHT_LISTING_APP_ID", "").strip()
    if not listing_app_id_raw:
        raise HTTPException(
            status_code=500,
            detail="INSIGHT_LISTING_APP_ID is not configured",
        )

    try:
        listing_app_id = int(listing_app_id_raw)
    except ValueError as err:
        raise HTTPException(
            status_code=500,
            detail="INSIGHT_LISTING_APP_ID is invalid",
        ) from err

    try:
        _ensure_listing_app_funded(listing_app_id)
        cid = await upload_insight_to_ipfs(payload.insight_text)
        listing_id, asa_id = store_cid_in_listing(
            cid=cid,
            listing_app_id=listing_app_id,
            seller_address=payload.seller_wallet,
        )
        tx_id = _find_cid_tx_id(listing_app_id, payload.seller_wallet, cid)
    except ListingStoreError as err:
        raise HTTPException(status_code=500, detail=str(err)) from err
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err)) from err

    return {
        "ok": "true",
        "txId": tx_id or "",
        "cid": cid,
        "listing_id": listing_id,
        "asa_id": asa_id,
        "explorer": (
            f"https://testnet.explorer.algorand.org/tx/{tx_id}"
            if tx_id
            else f"https://testnet.explorer.algorand.org/application/{listing_app_id}"
        ),
    }


__all__ = ["app", "upload_insight_to_ipfs", "store_cid_in_listing"]
