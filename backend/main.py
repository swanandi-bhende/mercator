"""FastAPI backend entrypoint for listing insights."""

from __future__ import annotations

import base64
import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from algosdk import mnemonic, transaction
from algosdk import encoding
from algosdk import account
from algosdk.logic import get_application_address
from algosdk.v2client import algod, indexer

try:
    from contracts.insight_listing import InsightListingClient  # noqa: F401
except Exception:  # pragma: no cover
    InsightListingClient = None  # type: ignore[assignment]

try:
    from utils.ipfs import (
        IPFSUploadError,
        ListingStoreError,
        upload_insight_to_ipfs,
        store_cid_in_listing,
    )
except ModuleNotFoundError:
    from backend.utils.ipfs import (
        IPFSUploadError,
        ListingStoreError,
        upload_insight_to_ipfs,
        store_cid_in_listing,
    )


load_dotenv()
load_dotenv(".env.testnet", override=True)

app = FastAPI(title="Mercator Backend")
logger = logging.getLogger("mercator.backend")


def _configure_logging() -> None:
    logs_dir = Path(__file__).resolve().parents[1] / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    if logger.handlers:
        return

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(logs_dir / "listing.log")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


_configure_logging()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ListingRequest(BaseModel):
    insight_text: str
    price: float
    seller_wallet: str


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
    pay_txn = transaction.PaymentTxn(
        sender=sender,
        sp=params,
        receiver=app_address,
        amt=top_up,
    )
    tx_id = client.send_transaction(pay_txn.sign(private_key))
    transaction.wait_for_confirmation(client, tx_id, 4)


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


async def _poll_for_listing_confirmation(
    *, app_id: int, sender: str, cid: str, max_seconds: int = 30
) -> str:
    waited = 0
    while waited <= max_seconds:
        tx_id = _find_cid_tx_id(app_id, sender, cid)
        if tx_id:
            return tx_id
        await asyncio.sleep(2)
        waited += 2
    raise HTTPException(
        status_code=504,
        detail="Transaction submitted but confirmation timed out",
    )


def _get_signing_mnemonic() -> str:
    seller_mnemonic = os.getenv("SELLER_MNEMONIC", "").strip()
    deployer_mnemonic = os.getenv("DEPLOYER_MNEMONIC", "").strip()
    selected = seller_mnemonic or deployer_mnemonic
    if not selected:
        raise HTTPException(
            status_code=500,
            detail="SELLER_MNEMONIC or DEPLOYER_MNEMONIC must be configured",
        )
    return selected


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/list")
async def create_listing(request: ListingRequest) -> dict[str, int | str]:
    load_dotenv()
    load_dotenv(".env.testnet", override=True)
    logger.info(
        "Incoming /list request: seller_wallet=%s, price=%s, insight_len=%s",
        request.seller_wallet,
        request.price,
        len(request.insight_text),
    )

    configured_signer_address = os.getenv("SELLER_ADDRESS", "").strip() or os.getenv(
        "DEPLOYER_ADDRESS", ""
    ).strip()

    wallet_prefix_or_signer_match = request.seller_wallet.startswith("7") or (
        configured_signer_address and request.seller_wallet == configured_signer_address
    )

    if (
        not request.insight_text.strip()
        or request.price <= 0
        or not wallet_prefix_or_signer_match
        or len(request.seller_wallet) != 58
        or not encoding.is_valid_address(request.seller_wallet)
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid insight text, price, or wallet address",
        )

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

    signing_mnemonic = _get_signing_mnemonic()
    signer_private_key = mnemonic.to_private_key(signing_mnemonic)
    signer_address = account.address_from_private_key(signer_private_key)
    if signer_address != request.seller_wallet:
        raise HTTPException(
            status_code=400,
            detail=(
                "seller_wallet does not match configured signing mnemonic address"
            ),
        )

    logger.info("Validation passed for seller %s", request.seller_wallet)

    try:
        _ensure_listing_app_funded(listing_app_id)

        cid = await upload_insight_to_ipfs(request.insight_text)
        logger.info("IPFS upload complete, cid=%s", cid)

        micro_price = int(request.price * 1_000_000)
        listing_id, asa_id = store_cid_in_listing(
            cid=cid,
            listing_app_id=listing_app_id,
            seller_address=request.seller_wallet,
            price=micro_price,
            signer_mnemonic=signing_mnemonic,
        )

        logger.info(
            "On-chain listing submitted: listing_id=%s asa_id=%s",
            listing_id,
            asa_id,
        )

        tx_id = await _poll_for_listing_confirmation(
            app_id=listing_app_id,
            sender=request.seller_wallet,
            cid=cid,
        )
        logger.info("Transaction confirmed: tx_id=%s", tx_id)
    except IPFSUploadError as err:
        logger.exception("IPFS upload failed")
        raise HTTPException(
            status_code=500,
            detail="Could not store insight on IPFS — please try again",
        ) from err
    except ListingStoreError as err:
        logger.exception("On-chain listing store failed")
        raise HTTPException(status_code=500, detail=str(err)) from err
    except Exception as err:
        logger.exception("Unexpected /list failure")
        raise HTTPException(status_code=500, detail=str(err)) from err

    return {
        "success": True,
        "transaction_id": tx_id,
        "txId": tx_id,
        "explorer_url": f"https://testnet.explorer.algorand.org/tx/{tx_id}",
        "message": "Insight listed on-chain and pinned on IPFS",
        "cid": cid,
        "listing_id": listing_id,
        "asa_id": asa_id,
    }


__all__ = ["app", "upload_insight_to_ipfs", "store_cid_in_listing"]
