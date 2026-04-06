"""FastAPI backend entrypoint for listing insights."""

from __future__ import annotations

import base64
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
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


def _safe_iso_from_round_time(round_time: object) -> str:
    if isinstance(round_time, (int, float)) and round_time > 0:
        return datetime.fromtimestamp(float(round_time), tz=timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


def _decode_app_args(app_args: list[object]) -> list[str]:
    decoded: list[str] = []
    for encoded_arg in app_args:
        if not isinstance(encoded_arg, str):
            continue
        try:
            decoded_value = base64.b64decode(encoded_arg).decode("utf-8", errors="ignore")
            if decoded_value:
                decoded.append(decoded_value)
        except Exception:
            continue
    return decoded


def _extract_cid_from_args(decoded_args: list[str]) -> str:
    for value in decoded_args:
        for token in value.replace("\n", " ").split(" "):
            if token.startswith("Qm") and len(token) >= 12:
                return token.strip()
    return ""


def _derive_action_type(txn: dict[str, object]) -> str:
    app_txn = txn.get("application-transaction") if isinstance(txn.get("application-transaction"), dict) else {}
    payment_txn = txn.get("payment-transaction") if isinstance(txn.get("payment-transaction"), dict) else {}
    asset_txn = txn.get("asset-transfer-transaction") if isinstance(txn.get("asset-transfer-transaction"), dict) else {}

    app_id = int(app_txn.get("application-id", 0) or 0) if isinstance(app_txn, dict) else 0
    listing_app_id = int(os.getenv("INSIGHT_LISTING_APP_ID", "0") or 0)
    escrow_app_id = int(os.getenv("ESCROW_APP_ID", "0") or 0)

    decoded_args = _decode_app_args(app_txn.get("application-args", []) if isinstance(app_txn, dict) else [])
    joined = " ".join(decoded_args).lower()

    if app_id and app_id == listing_app_id:
        return "listing_created"
    if app_id and app_id == escrow_app_id:
        if "release" in joined:
            return "escrow_released"
        return "payment_confirmed"

    if isinstance(asset_txn, dict) and int(asset_txn.get("amount", 0) or 0) > 0:
        return "payment_confirmed"
    if isinstance(payment_txn, dict) and int(payment_txn.get("amount", 0) or 0) > 0:
        return "payment_confirmed"

    if "deliver" in joined or "insight" in joined:
        return "insight_delivered"

    return "listing_created"


def _normalize_ledger_record(txn: dict[str, object]) -> dict[str, object]:
    app_txn = txn.get("application-transaction") if isinstance(txn.get("application-transaction"), dict) else {}
    payment_txn = txn.get("payment-transaction") if isinstance(txn.get("payment-transaction"), dict) else {}
    asset_txn = txn.get("asset-transfer-transaction") if isinstance(txn.get("asset-transfer-transaction"), dict) else {}

    tx_id = str(txn.get("id", ""))
    sender = str(txn.get("sender", ""))
    confirmed_round = int(txn.get("confirmed-round", 0) or 0)
    pool_error = str(txn.get("pool-error", "") or "")

    action_type = _derive_action_type(txn)
    status = "failed" if pool_error else ("confirmed" if confirmed_round > 0 else "pending")

    receiver = ""
    amount_micro = 0
    amount_usdc = 0.0

    if isinstance(asset_txn, dict):
        receiver = str(asset_txn.get("receiver", ""))
        amount_micro = int(asset_txn.get("amount", 0) or 0)
        amount_usdc = amount_micro / 1_000_000
    elif isinstance(payment_txn, dict):
        receiver = str(payment_txn.get("receiver", ""))
        amount_micro = int(payment_txn.get("amount", 0) or 0)
        amount_usdc = amount_micro / 1_000_000

    app_id = int(app_txn.get("application-id", 0) or 0) if isinstance(app_txn, dict) else 0
    app_args = app_txn.get("application-args", []) if isinstance(app_txn, dict) else []
    decoded_args = _decode_app_args(app_args if isinstance(app_args, list) else [])
    cid = _extract_cid_from_args(decoded_args)

    first_valid_time = txn.get("round-time")
    timestamp_iso = _safe_iso_from_round_time(first_valid_time)

    listing_id = ""
    if isinstance(txn.get("note"), str) and txn.get("note"):
        listing_id = str(txn.get("note"))

    fee_micro = int(txn.get("fee", 0) or 0)

    return {
        "id": tx_id or f"idx-{hash(json.dumps(txn, default=str))}",
        "timestampIso": timestamp_iso,
        "actionType": action_type,
        "seller": sender or "Unknown",
        "buyer": receiver or "-",
        "amountUsdc": amount_usdc,
        "status": status,
        "txId": tx_id,
        "explorerUrl": f"{EXPLORER_TX_BASE}/{tx_id}/" if tx_id else "",
        "cid": cid or "",
        "ipfsUrl": f"https://ipfs.io/ipfs/{cid}" if cid else "",
        "listingId": listing_id or "",
        "contractId": f"app:{app_id}" if app_id else "payment",
        "confirmationRound": confirmed_round,
        "feeAlgo": f"{fee_micro / 1_000_000:.6f}",
        "escrowStatus": "released" if action_type == "escrow_released" else ("locked" if action_type == "payment_confirmed" else "n/a"),
        "contentHash": "",
        "listingMetadata": " | ".join(decoded_args) if decoded_args else "",
        "errorMessage": pool_error or "",
    }


def _is_mercator_transaction(txn: dict[str, object]) -> bool:
    app_txn = txn.get("application-transaction") if isinstance(txn.get("application-transaction"), dict) else {}
    payment_txn = txn.get("payment-transaction") if isinstance(txn.get("payment-transaction"), dict) else {}
    asset_txn = txn.get("asset-transfer-transaction") if isinstance(txn.get("asset-transfer-transaction"), dict) else {}

    listing_app_id = int(os.getenv("INSIGHT_LISTING_APP_ID", "0") or 0)
    escrow_app_id = int(os.getenv("ESCROW_APP_ID", "0") or 0)
    app_id = int(app_txn.get("application-id", 0) or 0) if isinstance(app_txn, dict) else 0

    if app_id and app_id in {listing_app_id, escrow_app_id}:
        return True

    known_wallets = {
      os.getenv("DEPLOYER_ADDRESS", "").strip(),
      os.getenv("SELLER_ADDRESS", "").strip(),
      os.getenv("BUYER_ADDRESS", "").strip(),
      os.getenv("BUYER_WALLET", "").strip(),
    }
    known_wallets = {wallet for wallet in known_wallets if wallet}

    sender = str(txn.get("sender", ""))
    receiver = ""
    if isinstance(asset_txn, dict):
        receiver = str(asset_txn.get("receiver", ""))
    elif isinstance(payment_txn, dict):
        receiver = str(payment_txn.get("receiver", ""))

    if known_wallets and (sender in known_wallets or receiver in known_wallets):
        return True

    decoded_args = _decode_app_args(app_txn.get("application-args", []) if isinstance(app_txn, dict) else [])
    if _extract_cid_from_args(decoded_args):
        return True

    return False


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
def health() -> dict[str, object]:
    normalize_network_env()
    timestamp = datetime.now(timezone.utc).isoformat()

    services: dict[str, dict[str, str]] = {
        "api": {"status": "ok", "detail": "FastAPI service is running"},
        "algod": {"status": "unknown", "detail": "Not checked"},
        "indexer": {"status": "unknown", "detail": "Not checked"},
        "listing_app": {"status": "unknown", "detail": "Not checked"},
        "escrow_app": {"status": "unknown", "detail": "Not checked"},
    }

    overall_status = "ok"

    try:
        algod_client = _get_algod_client()
        params = algod_client.suggested_params()
        if params is None:
            raise RuntimeError("No suggested params returned")
        services["algod"] = {"status": "ok", "detail": "Connected"}
    except Exception as err:
        overall_status = "degraded"
        services["algod"] = {"status": "error", "detail": str(err)}

    try:
        idx = _get_indexer_client()
        idx.search_transactions(limit=1)
        services["indexer"] = {"status": "ok", "detail": "Connected"}
    except Exception as err:
        overall_status = "degraded"
        services["indexer"] = {"status": "error", "detail": str(err)}

    listing_app = os.getenv("INSIGHT_LISTING_APP_ID", "").strip()
    if listing_app and listing_app.isdigit() and int(listing_app) > 0:
        services["listing_app"] = {"status": "ok", "detail": f"Configured ({listing_app})"}
    else:
        overall_status = "degraded"
        services["listing_app"] = {"status": "error", "detail": "INSIGHT_LISTING_APP_ID missing/invalid"}

    escrow_app = os.getenv("ESCROW_APP_ID", "").strip()
    if escrow_app and escrow_app.isdigit() and int(escrow_app) > 0:
        services["escrow_app"] = {"status": "ok", "detail": f"Configured ({escrow_app})"}
    else:
        overall_status = "degraded"
        services["escrow_app"] = {"status": "error", "detail": "ESCROW_APP_ID missing/invalid"}

    return {
        "status": overall_status,
        "timestamp": timestamp,
        "services": services,
    }


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


@app.get("/ledger")
async def ledger_feed(
    limit: int = 250,
    next_token: str | None = None,
    address: str | None = None,
    max_scan_pages: int = 12,
) -> dict[str, object]:
    """Return normalized ledger records from Algorand indexer transactions."""
    normalize_network_env()
    idx = _get_indexer_client()

    safe_limit = max(1, min(limit, 1000))

    try:
        current_token = next_token
        records: list[dict[str, object]] = []
        record_ids: set[str] = set()
        pages_scanned = 0
        max_pages = max(1, min(max_scan_pages, 50))

        listing_app_id = int(os.getenv("INSIGHT_LISTING_APP_ID", "0") or 0)
        escrow_app_id = int(os.getenv("ESCROW_APP_ID", "0") or 0)

        targeted_queries: list[dict[str, object]] = []
        if listing_app_id > 0:
            targeted_queries.append({"application_id": listing_app_id})
        if escrow_app_id > 0:
            targeted_queries.append({"application_id": escrow_app_id})
        if address:
            targeted_queries.append({"address": address})

        for query_filters in targeted_queries:
            local_token = current_token
            local_scans = 0
            while local_scans < max_pages and len(records) < safe_limit:
                search_params: dict[str, object] = {
                    "limit": safe_limit,
                    **query_filters,
                }
                if local_token:
                    search_params["next_page"] = local_token

                response = idx.search_transactions(**search_params)
                raw_transactions = response.get("transactions", [])
                transactions = raw_transactions if isinstance(raw_transactions, list) else []

                for txn in transactions:
                    if not isinstance(txn, dict) or not _is_mercator_transaction(txn):
                        continue
                    normalized = _normalize_ledger_record(txn)
                    rec_id = str(normalized.get("id", ""))
                    if rec_id and rec_id not in record_ids:
                        record_ids.add(rec_id)
                        records.append(normalized)

                local_scans += 1
                pages_scanned += 1
                next_page_token = response.get("next-token")
                local_token = str(next_page_token) if isinstance(next_page_token, str) and next_page_token else None
                if not local_token:
                    break

            if len(records) >= safe_limit:
                break

        while pages_scanned < max_pages and len(records) < safe_limit:
            search_params: dict[str, object] = {
                "limit": safe_limit,
            }
            if current_token:
                search_params["next_page"] = current_token
            if address:
                search_params["address"] = address

            response = idx.search_transactions(**search_params)
            raw_transactions = response.get("transactions", [])
            transactions = raw_transactions if isinstance(raw_transactions, list) else []

            mercator_txns = [txn for txn in transactions if isinstance(txn, dict) and _is_mercator_transaction(txn)]
            for txn in mercator_txns:
                normalized = _normalize_ledger_record(txn)
                rec_id = str(normalized.get("id", ""))
                if rec_id and rec_id not in record_ids:
                    record_ids.add(rec_id)
                    records.append(normalized)

            pages_scanned += 1
            next_page_token = response.get("next-token")
            current_token = str(next_page_token) if isinstance(next_page_token, str) and next_page_token else None
            if not current_token:
                break

        records = records[:safe_limit]

        records.sort(
            key=lambda item: str(item.get("timestampIso", "")),
            reverse=True,
        )

        return {
            "success": True,
            "records": records,
            "count": len(records),
            "nextToken": current_token,
            "source": "indexer",
            "pagesScanned": pages_scanned,
        }
    except HTTPException:
        raise
    except Exception as err:
        logger.error("Ledger feed failed | error=%s", err, exc_info=True)
        return {
            "success": False,
            "records": [],
            "count": 0,
            "nextToken": None,
            "source": "indexer",
            "error": str(err),
        }


__all__ = ["app", "upload_insight_to_ipfs", "store_cid_in_listing"]
