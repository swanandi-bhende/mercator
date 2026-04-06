"""FastAPI backend entrypoint for listing insights."""

from __future__ import annotations

import base64
import asyncio
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from algosdk import mnemonic, transaction
from algosdk import encoding
from algosdk import account
from algosdk.logic import get_application_address
from algosdk.v2client import algod, indexer

from backend.agent import run_agent
from backend.tools.semantic_search import semantic_search as semantic_search_tool
from backend.utils.runtime_env import configure_demo_logging, normalize_network_env, warn_missing_required_env
from backend.utils.error_handler import contract_error, ipfs_down

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


normalize_network_env()
demo_logger = configure_demo_logging()

app = FastAPI(title="Mercator Backend")
logger = logging.getLogger("mercator.backend")

EXPLORER_TX_BASE = os.getenv("EXPLORER_TX_BASE", "https://explorer.perawallet.app/tx").rstrip("/")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("mercator.log", mode="a"),
    ],
    force=True,
)


def _error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message})

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ListingRequest(BaseModel):
    insight_text: str
    price: float
    seller_wallet: str


class DemoPurchaseRequest(BaseModel):
    user_query: str
    buyer_address: str | None = None
    user_approval_input: str = "approve"
    force_buy_for_test: bool = True


class DiscoverRequest(BaseModel):
    user_query: str


def _get_algod_client() -> algod.AlgodClient:
    normalize_network_env()
    algod_url = os.getenv("ALGOD_URL", "").strip() or os.getenv("ALGOD_SERVER", "").strip()
    if not algod_url:
        raise HTTPException(status_code=500, detail="ALGOD_URL/ALGOD_SERVER is not configured")
    token = os.getenv("ALGOD_TOKEN", "").strip()
    return algod.AlgodClient(algod_token=token, algod_address=algod_url)


def _get_indexer_client() -> indexer.IndexerClient:
    normalize_network_env()
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


@app.on_event("startup")
def startup_checks() -> None:
    normalize_network_env()
    warn_missing_required_env(logger)


def _extract_final_insight_text(result: dict[str, object]) -> str:
    payment_status = result.get("payment_status")
    if isinstance(payment_status, dict):
        post_payment_output = payment_status.get("post_payment_output")
        if isinstance(post_payment_output, str):
            marker = "Here is your human trading insight:\n\n"
            if marker in post_payment_output:
                return post_payment_output.split(marker, 1)[-1].split("\n\nTransaction IDs:", 1)[0].strip()
            return post_payment_output.strip()
    return ""


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
    normalize_network_env()
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
        return _error_response(400, "Invalid insight text, price, or wallet address")

    listing_app_id_raw = os.getenv("INSIGHT_LISTING_APP_ID", "").strip()
    if not listing_app_id_raw:
        return _error_response(500, "INSIGHT_LISTING_APP_ID is not configured")

    try:
        listing_app_id = int(listing_app_id_raw)
    except ValueError as err:
        logger.error("Invalid listing app id in environment | value=%s", listing_app_id_raw)
        return _error_response(500, "INSIGHT_LISTING_APP_ID is invalid")

    signing_mnemonic = _get_signing_mnemonic()
    signer_private_key = mnemonic.to_private_key(signing_mnemonic)
    signer_address = account.address_from_private_key(signer_private_key)
    if signer_address != request.seller_wallet:
        return _error_response(
            400,
            "seller_wallet does not match configured signing mnemonic address",
        )

    logger.info("Validation passed for seller %s", request.seller_wallet)

    try:
        _ensure_listing_app_funded(listing_app_id)

        logger.info("IPFS upload started | seller=%s", request.seller_wallet)
        cid = await upload_insight_to_ipfs(request.insight_text)
        logger.info("IPFS upload complete, cid=%s", cid)

        micro_price = int(request.price * 1_000_000)
        logger.info(
            "ASA creation attempted | seller=%s price_micro=%s app_id=%s",
            request.seller_wallet,
            micro_price,
            listing_app_id,
        )
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
        demo_logger.info("Seller upload complete")
        demo_logger.info("On-chain ASA created")

        tx_id = await _poll_for_listing_confirmation(
            app_id=listing_app_id,
            sender=request.seller_wallet,
            cid=cid,
        )
        logger.info("Transaction confirmed: tx_id=%s", tx_id)
    except IPFSUploadError as err:
        logger.error("IPFS upload failed | error=%s", err, exc_info=True)
        return _error_response(500, ipfs_down(logger, str(err)))
    except ListingStoreError as err:
        logger.error("ASA creation failed | error=%s", err, exc_info=True)
        return _error_response(500, contract_error(logger, str(err)))
    except HTTPException as err:
        logger.error("Transaction confirmation failed | detail=%s", err.detail, exc_info=True)
        return _error_response(err.status_code, str(err.detail))
    except Exception as err:
        logger.error("Unexpected /list failure | error=%s", err, exc_info=True)
        return _error_response(500, "Transaction failed - please try again")

    return {
        "success": True,
        "transaction_id": tx_id,
        "txId": tx_id,
        "explorer_url": f"{EXPLORER_TX_BASE}/{tx_id}/",
        "message": "Insight listed on-chain and pinned on IPFS",
        "cid": cid,
        "listing_id": listing_id,
        "asa_id": asa_id,
    }


@app.post("/demo_purchase")
async def demo_purchase(request: DemoPurchaseRequest) -> dict[str, object]:
    normalize_network_env()
    buyer_address = (request.buyer_address or os.getenv("BUYER_WALLET", "").strip() or os.getenv("BUYER_ADDRESS", "").strip() or os.getenv("DEPLOYER_ADDRESS", "").strip())
    result = await run_agent(
        user_query=request.user_query,
        buyer_address=buyer_address,
        user_approval_input=request.user_approval_input,
        force_buy_for_test=request.force_buy_for_test,
    )

    final_insight_text = _extract_final_insight_text(result if isinstance(result, dict) else {})
    return {
        "success": bool(result.get("success", False)) if isinstance(result, dict) else False,
        "final_insight_text": final_insight_text,
        "result": result,
    }


@app.post("/discover")
async def discover_insights(request: DiscoverRequest) -> dict[str, object]:
    normalize_network_env()
    user_query = request.user_query.strip()
    if not user_query:
        return {
            "success": True,
            "query": "",
            "matches": [],
            "message": "Empty query",
            "degraded": False,
            "diagnostics": {
                "code": "EMPTY_QUERY",
                "detail": "No query provided",
            },
        }

    try:
        raw = await semantic_search_tool.ainvoke({"query": user_query})
        parsed: dict[str, object]
        if isinstance(raw, str):
            parsed = json.loads(raw)
        elif isinstance(raw, dict):
            parsed = raw
        else:
            parsed = {"query": user_query, "matches": []}

        return {
            "success": True,
            "query": str(parsed.get("query", user_query)),
            "embedding_fallback": bool(parsed.get("embedding_fallback", False)),
            "matches": parsed.get("matches", []) if isinstance(parsed.get("matches", []), list) else [],
            "message": parsed.get("message") if isinstance(parsed.get("message"), str) else None,
            "degraded": False,
            "diagnostics": {
                "code": "OK",
                "detail": "Ranked insights returned",
            },
        }
    except Exception as err:
        logger.error("Discover search failed | error=%s", err, exc_info=True)
        return {
            "success": True,
            "query": user_query,
            "embedding_fallback": True,
            "matches": [],
            "message": "Ranking is temporarily unavailable. Please retry shortly.",
            "degraded": True,
            "diagnostics": {
                "code": "DISCOVER_RANKING_FAILED",
                "detail": str(err),
            },
        }


__all__ = ["app", "upload_insight_to_ipfs", "store_cid_in_listing"]
