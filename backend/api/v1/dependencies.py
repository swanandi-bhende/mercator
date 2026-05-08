from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from typing import DefaultDict

from fastapi import HTTPException, Request, Response

from .auth import lookup_api_key, update_last_used
from .responses import generate_request_id
from backend.utils import db as _db



# In-memory sliding windows per key_id. Resets on process restart.
_request_windows: DefaultDict[str, deque] = defaultdict(deque)


async def verify_api_key(request: Request) -> dict:
    provided = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    # assign request id early so it's available to all downstream deps and handlers
    request_id = generate_request_id()
    request.state.request_id = request_id
    if not provided:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "MISSING_API_KEY",
                "message": "Provide your API key in the X-API-Key header or api_key query parameter",
                "details": {"docs_url": "https://your-staging-url/api/v1/docs"},
            },
        )

    key_record = lookup_api_key(provided)
    if not key_record:
        raise HTTPException(
            status_code=403,
            detail={"code": "INVALID_API_KEY", "message": "API key not found or deactivated", "details": {}},
        )

    # Attach key record to request.state so later dependencies and handlers can reuse it
    request.state.api_key_record = key_record

    # Fire-and-forget update of last used timestamp and request count
    try:
        asyncio.create_task(asyncio.to_thread(update_last_used, key_record["key_id"]))
    except Exception:
        # Non-fatal: do not block request on metrics update
        pass

    return key_record



async def log_request(request: Request, response: Response):
    start_time = time.monotonic()
    request_id = getattr(request.state, "request_id", None)
    try:
        yield
    finally:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        key_record = getattr(request.state, "api_key_record", {}) or {}
        key_id = key_record.get("key_id")
        endpoint = request.url.path
        method = request.method
        status = getattr(response, "status_code", None) or 0
        requested_at = _db._utc_now_iso() if hasattr(_db, "_utc_now_iso") else None
        # Insert into api_request_log table
        try:
            _db.initialise_curator_schema()
            with _db._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO api_request_log (
                        request_id, key_id, endpoint, method, request_body_summary, response_status, response_time_ms, requested_at, ip_address
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request_id,
                        key_id,
                        endpoint,
                        method,
                        None,
                        int(status),
                        int(duration_ms),
                        requested_at,
                        request.client.host if request.client else None,
                    ),
                )
                conn.commit()
        except Exception:
            # Logging should never block the request path
            pass



async def check_rate_limit(request: Request, response: Response) -> None:
    key_record = getattr(request.state, "api_key_record", None)
    if not key_record:
        raise HTTPException(
            status_code=500,
            detail={"code": "MISSING_KEY_RECORD", "message": "Authentication dependency did not run", "details": {}},
        )

    key_id = key_record["key_id"]
    limit = int(key_record.get("rate_limit_per_minute", 60))
    now = time.time()
    window = _request_windows[key_id]

    # drop old timestamps
    while window and window[0] < now - 60:
        window.popleft()

    if len(window) >= limit:
        retry_after = int(60 - (now - window[0]))
        headers = {
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(window[0] + 60)),
        }
        raise HTTPException(
            status_code=429,
            headers=headers,
            detail={
                "code": "RATE_LIMIT_EXCEEDED",
                "message": f"Rate limit of {limit} requests per minute exceeded",
                "details": {"retry_after_seconds": retry_after, "tier": key_record.get("tier")},
            },
        )

    # record this request
    window.append(now)

    # add helpful headers to the response
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(limit - len(window))
