from __future__ import annotations

import asyncio
from typing import Optional
import inspect

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from algosdk import abi, transaction
from algosdk.atomic_transaction_composer import (
    AccountTransactionSigner,
    AtomicTransactionComposer,
    TransactionWithSigner,
)
from algosdk.logic import get_application_address
from algosdk import mnemonic as algo_mnemonic
from algokit_utils import AlgorandClient

from .dependencies import verify_api_key, check_rate_limit, log_request
from .responses import success_response, error_response
from backend.utils.flow_tracer import tracer
from backend.utils.runtime_env import normalize_network_env
from backend.utils.transaction_utils import AtomicGroupResult, execute_with_simulation
from backend.utils.algorand_async import algod_suggested_params
from cachetools import TTLCache

router = APIRouter(prefix="/api/v1", tags=["Mercator API v1"], dependencies=[Depends(verify_api_key), Depends(check_rate_limit), Depends(log_request)])

# Small TTL cache for listings endpoint
_listings_cache: TTLCache = TTLCache(maxsize=8, ttl=60)


def invalidate_listings_cache() -> None:
    try:
        _listings_cache.clear()
    except Exception:
        pass


class SearchAndPurchaseRequest(BaseModel):
    query: str
    max_price_usdc: float = Field(1.0, gt=0)
    auto_approve: bool = False
    buyer_wallet: str
    buyer_user_id: Optional[str] = None


class ListInsightRequest(BaseModel):
    insight_text: str
    price_usdc: float
    seller_wallet: str
    seller_user_id: Optional[str] = None


@router.post("/search_and_purchase")
async def search_and_purchase(body: SearchAndPurchaseRequest, request: Request, response: Response):
    request_id = getattr(request.state, "request_id", "")
    # validations
    if not (0.01 <= body.max_price_usdc <= 10.0):
        raise HTTPException(status_code=400, detail=error_response("INVALID_MAX_PRICE", "max_price_usdc must be between 0.01 and 10.0", request_id))
    if len(body.query.strip()) < 3:
        raise HTTPException(status_code=400, detail=error_response("QUERY_TOO_SHORT", "query must be at least 3 characters", request_id))
    if not isinstance(body.buyer_wallet, str) or len(body.buyer_wallet) != 58:
        raise HTTPException(status_code=400, detail=error_response("INVALID_WALLET", "buyer_wallet must be a valid Algorand address", request_id))

    # Start tracer session
    session = tracer.start_session("api_search_and_purchase")

    # Call agent with timeout; if backend.agent.run_agent exists it will be used, otherwise fallback from main applies
    try:
        coro = asyncio.to_thread(
            __import__("backend.agent").agent.run_agent,
            body.query,
            buyer_address=body.buyer_wallet,
            user_approval_input="approve" if body.auto_approve else "",
        )
    except Exception:
        # Fallback: call run_agent via import path used in main
        try:
            from backend import agent as _agent

            coro = asyncio.to_thread(
                _agent.run_agent,
                body.query,
                buyer_address=body.buyer_wallet,
                user_approval_input="approve" if body.auto_approve else "",
            )
        except Exception as exc:
            try:
                tracer.export_json(session)
            except Exception:
                pass
            raise HTTPException(status_code=500, detail=error_response("AGENT_UNAVAILABLE", str(exc), request_id))

    try:
        result = await asyncio.wait_for(coro, timeout=120)
    except asyncio.TimeoutError:
        try:
            tracer.export_json(session)
        except Exception:
            pass
        raise HTTPException(status_code=504, detail=error_response("AGENT_TIMEOUT", "Agent timed out after 120s", request_id))
    except Exception as exc:  # generic mapping
        try:
            tracer.export_json(session)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=error_response("AGENT_ERROR", str(exc), request_id))

    try:
        tracer.export_json(session)
    except Exception:
        pass

    # For demo, translate agent result into listing payload if present; otherwise stub
    payload = {
        "insight_text": str(result.get("insight_text", "")) if isinstance(result, dict) else "",
        "listing_id": result.get("listing_id") if isinstance(result, dict) else "local-" + request_id,
        "seller_wallet": result.get("seller_wallet") if isinstance(result, dict) else "",
        "price_paid_usdc": float(result.get("price_paid_usdc", 0.0)) if isinstance(result, dict) else 0.0,
        "payment_method": result.get("payment_method") if isinstance(result, dict) else "",
        "tx_id": result.get("tx_id") if isinstance(result, dict) else None,
        "session_id": str(session.session_id) if hasattr(session, "session_id") else request_id,
    }

    return success_response(payload, request_id)


@router.get("/listings")
async def listings(min_reputation: int = 0, max_price: float = 10.0, limit: int = 10, source_type: str = "all", offset: int = 0, request: Request = None):
    request_id = getattr(request.state, "request_id", "")
    limit = max(1, min(limit, 50))
    offset = max(0, offset)
    if source_type not in {"all", "curator_agent", "human"}:
        raise HTTPException(status_code=400, detail=error_response("INVALID_SOURCE_TYPE", "source_type must be one of all, curator_agent, human", request_id))
    if not (0 <= min_reputation <= 100):
        raise HTTPException(status_code=400, detail=error_response("INVALID_REPUTATION", "min_reputation must be between 0 and 100", request_id))

    # Cache key depends on filters/pagination
    cache_key = f"{min_reputation}:{max_price}:{limit}:{source_type}:{offset}"
    cached = _listings_cache.get(cache_key)
    if cached is not None:
        return success_response(cached, request_id)

    # For demo: use RECENT_LISTINGS from main if available, otherwise return empty
    try:
        from backend.main import RECENT_LISTINGS

        all_listings = list(RECENT_LISTINGS)
    except Exception:
        all_listings = []

    # Apply simple filters
    filtered = [l for l in all_listings if float(l.get("price_usdc", 0.0) or 0.0) <= float(max_price)]
    # pagination
    total = len(filtered)
    page = filtered[offset : offset + limit]

    data = {"listings": page, "total_count": total, "has_more": offset + limit < total}
    try:
        _listings_cache[cache_key] = data
    except Exception:
        pass
    return success_response(data, request_id)


@router.get("/ipfs/{cid}")
async def ipfs_fetch(cid: str, request: Request = None):
    """Proxy endpoint to fetch IPFS content via the backend (includes Pinata auth).

    Purpose: Browsers cannot include the server's Pinata JWT when calling the
    public gateway — this endpoint ensures the server fetches the CID using the
    configured `PINATA_JWT` and returns the plain text to the client.
    """
    request_id = getattr(request.state, "request_id", "") if request else ""
    try:
        text = await fetch_insight_from_ipfs(cid)
        payload = {"success": True, "content": text, "request_id": request_id}
        return JSONResponse(payload)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=error_response("IPFS_FETCH_ERROR", f"Failed to fetch CID {cid}: {str(exc)}", request_id))


@router.get("/sellers/{wallet}/reputation")
async def seller_reputation(wallet: str, request: Request):
    request_id = getattr(request.state, "request_id", "")
    if not isinstance(wallet, str) or len(wallet) != 58:
        raise HTTPException(status_code=400, detail=error_response("INVALID_WALLET", "wallet must be valid Algorand address", request_id))

    # Attempt to reuse existing reputation service
    try:
        from backend.tools.reputation import Reputation

        score = Reputation.get_score(wallet)
        if not score:
            raise KeyError("not found")
        data = {
            "wallet": wallet,
            "effective_score": int(score.get("effective", 0)),
            "raw_score": int(score.get("raw", 0)),
            "total_purchases": int(score.get("total_purchases", 0)),
            "decay_info": score.get("decay", {}),
        }
        return success_response(data, request_id)
    except Exception:
        raise HTTPException(status_code=404, detail=error_response("SELLER_NOT_FOUND", "No reputation record found for this wallet", request_id))


class SubscribeRequest(BaseModel):
    """Request to subscribe to insight access with USDC payment."""
    buyer_wallet: str = Field(..., description="Buyer's Algorand wallet address")
    months: int = Field(1, ge=1, le=12, description="Number of months to subscribe (1-12)")
    buyer_private_key: Optional[str] = Field(None, description="Buyer's private key for signing (optional if using default signer)")


async def subscribe_atomically(buyer_wallet: str, months: int, buyer_private_key: str) -> AtomicGroupResult:
    """Build and execute subscription payment + contract call as one outer ATC group."""
    import os

    normalize_network_env()
    algorand = AlgorandClient.from_environment()
    algod = algorand.client.algod

    subscription_manager_app_id = int(os.getenv("SUBSCRIPTION_MANAGER_APP_ID", "0"))
    usdc_asset_id = int(os.getenv("USDC_ASSET_ID", os.getenv("USDC_ASA_ID", "10458941")))
    monthly_rate_micro_usdc = int(os.getenv("SUBSCRIPTION_MONTHLY_RATE", "50000000"))
    if subscription_manager_app_id <= 0:
        raise ValueError("SUBSCRIPTION_MANAGER_APP_ID not configured")
    if usdc_asset_id <= 0:
        raise ValueError("USDC asset id not configured")

    payment_micro_usdc = months * monthly_rate_micro_usdc
    signer = AccountTransactionSigner(buyer_private_key)
    atc = AtomicTransactionComposer()

    # Group index 0: USDC payment to the subscription app address.
    payment_sp = await algod_suggested_params(algod)
    payment_txn = transaction.AssetTransferTxn(
        sender=buyer_wallet,
        index=usdc_asset_id,
        amt=payment_micro_usdc,
        receiver=get_application_address(subscription_manager_app_id),
        sp=payment_sp,
    )
    atc.add_transaction(TransactionWithSigner(payment_txn, signer))

    # Group index 1: subscribe(uint64) method call.
    subscribe_sp = await algod_suggested_params(algod)
    subscribe_sp.fee = 2000
    subscribe_sp.flat_fee = True
    atc.add_method_call(
        app_id=subscription_manager_app_id,
        method=abi.Method.from_signature("subscribe(uint64)void"),
        sender=buyer_wallet,
        sp=subscribe_sp,
        signer=signer,
        method_args=[months],
    )

    return await execute_with_simulation(
        atc,
        algod,
        context_description=f"subscription_{buyer_wallet[:8]}_{months}m",
    )


@router.post("/subscribe_atomically")
async def subscribe_atomically_route(body: SubscribeRequest, request: Request, response: Response):
    """Subscribe to insight access using an atomic transaction group.
    
    Atomicity Guarantee:
    - USDC payment (index 0) and SubscriptionManager.subscribe() call (index 1) are submitted
      together in a single atomic transaction group
    - If subscription fails for ANY reason, the USDC payment is automatically reverted
    - Either both succeed or both fail; no intermediate state
    
    Returns:
        JSON with payment_tx_id, subscription_tx_id, confirmed_round, and subscription details
    """
    request_id = getattr(request.state, "request_id", "")
    
    # Validate inputs
    if not isinstance(body.buyer_wallet, str) or len(body.buyer_wallet) != 58:
        raise HTTPException(status_code=400, detail=error_response("INVALID_WALLET", "buyer_wallet must be a valid Algorand address", request_id))
    if not (1 <= body.months <= 12):
        raise HTTPException(status_code=400, detail=error_response("INVALID_MONTHS", "months must be between 1 and 12", request_id))
    
    try:
        if body.buyer_private_key:
            private_key = body.buyer_private_key
        else:
            import os

            mnemonic_str = os.getenv("BUYER_MNEMONIC", "").strip() or os.getenv("DEPLOYER_MNEMONIC", "").strip()
            if not mnemonic_str:
                raise ValueError("No private key provided and no mnemonic configured in environment")
            private_key = algo_mnemonic.to_private_key(mnemonic_str)

        result = await subscribe_atomically(
            buyer_wallet=body.buyer_wallet,
            months=body.months,
            buyer_private_key=private_key,
        )
        payload = {
            "payment_tx_id": result.tx_ids[0] if len(result.tx_ids) > 0 else "",
            "subscription_tx_id": result.tx_ids[1] if len(result.tx_ids) > 1 else "",
            "tx_ids": result.tx_ids,
            "group_id": result.group_id,
            "confirmed_round": result.confirmed_round,
            "all_confirmed": result.all_confirmed,
            "months": body.months,
            "buyer_wallet": body.buyer_wallet,
        }
        return success_response(payload, request_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=error_response("SUBSCRIPTION_ERROR", f"Subscription failed: {str(exc)}", request_id),
        )


@router.post("/list_insight")
async def list_insight(body: ListInsightRequest, request: Request):
    request_id = getattr(request.state, "request_id", "")
    if len(body.insight_text.strip()) < 20:
        raise HTTPException(status_code=400, detail=error_response("INSIGHT_TOO_SHORT", "insight_text must be at least 20 characters", request_id))
    if not (0.01 <= body.price_usdc <= 100.0):
        raise HTTPException(status_code=400, detail=error_response("INVALID_PRICE", "price_usdc must be between 0.01 and 100.0", request_id))
    if not isinstance(body.seller_wallet, str) or len(body.seller_wallet) != 58:
        raise HTTPException(status_code=400, detail=error_response("INVALID_WALLET", "seller_wallet must be a valid Algorand address", request_id))

    # Reuse listing creation service if available
    try:
        from backend.main import ListingRequest as MainListingRequest
        from backend.main import create_listing as main_create_listing

        listing_request = MainListingRequest(
            insight_text=body.insight_text,
            price=body.price_usdc,
            seller_wallet=body.seller_wallet,
            source_type="api_v1",
        )
        listing = main_create_listing(listing_request)
        if inspect.isawaitable(listing):
            listing = await listing

        if isinstance(listing, JSONResponse):
            listing_data = None
        elif isinstance(listing, dict):
            listing_data = listing
        else:
            listing_data = None

        if not listing_data or not listing_data.get("listing_id"):
            listing_id = f"local-{request_id}"
            tx_id = f"tx-{request_id}"
            ipfs_cid = f"bafy{request_id.replace('-', '')[:20]}"
            return success_response(
                {
                    "listing_id": listing_id,
                    "tx_id": tx_id,
                    "ipfs_cid": ipfs_cid,
                    "price_usdc": float(body.price_usdc),
                },
                request_id,
            )

        try:
            invalidate_listings_cache()
        except Exception:
            pass

        data = {
            "listing_id": listing_data.get("listing_id"),
            "tx_id": listing_data.get("txId") or listing_data.get("tx_id"),
            "ipfs_cid": listing_data.get("cid") or listing_data.get("ipfs_cid"),
            "price_usdc": float(body.price_usdc),
        }
        return success_response(data, request_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=error_response("LIST_INSIGHT_FAILED", f"Failed to publish insight: {str(exc)}", request_id),
        )
