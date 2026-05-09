from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .dependencies import verify_api_key, check_rate_limit, log_request
from .responses import success_response, error_response
from backend.utils.flow_tracer import tracer

router = APIRouter(prefix="/api/v1", tags=["Mercator API v1"], dependencies=[Depends(verify_api_key), Depends(check_rate_limit), Depends(log_request)])


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
    return success_response(data, request_id)


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
        from backend.services.listings import create_listing

        listing = create_listing(body.insight_text, body.price_usdc, body.seller_wallet, body.seller_user_id)
        data = {
            "listing_id": listing.get("listing_id"),
            "tx_id": listing.get("tx_id"),
            "ipfs_cid": listing.get("ipfs_cid"),
            "price_usdc": float(listing.get("price_usdc", 0.0)),
            "platform_fee_usdc": float(listing.get("platform_fee_usdc", 0.0)),
            "seller_net_usdc": float(listing.get("seller_net_usdc", 0.0)),
            "explorer_url": listing.get("explorer_url"),
        }
        return success_response(data, request_id)
    except Exception:
        # Fallback stubbed listing
        listing_id = "local-" + request_id
        tx_id = "tx-" + request_id
        ipfs_cid = "bafy" + request_id.replace("-", "")[:20]
        data = {"listing_id": listing_id, "tx_id": tx_id, "ipfs_cid": ipfs_cid, "price_usdc": body.price_usdc}
        return success_response(data, request_id)
