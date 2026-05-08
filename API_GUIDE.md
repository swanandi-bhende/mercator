# Mercator API Guide

## Global response envelope

All API responses use this envelope exactly:

{
  "success": boolean,
  "data": object | null,
  "error": {"code": string, "message": string, "details": object} | null,
  "request_id": string,    # UUID4 generated at request start
  "timestamp": string      # ISO8601 UTC
}

- On success: `success: true`, `data` populated, `error: null`.
- On failure: `success: false`, `data: null`, `error` populated.

Include `request_id` in every log line to correlate requests with support traces.

## Authentication

- API key must be provided in `X-API-Key` header or `?api_key=` query parameter.
- API keys are stored hashed (SHA-256) in the `api_keys` table; plaintext is only returned once at creation.
- Router-level dependency `verify_api_key` sets `request.state.api_key_record` with the key record for downstream use.

## Rate limiting

- Rate limiting is implemented as a router-level dependency (`check_rate_limit`) so it runs after authentication and can apply per-key limits.
- Tiers and limits:
  - demo: 10 requests / minute
  - developer: 60 requests / minute
  - enterprise: 600 requests / minute
- Implementation note: current implementation uses an in-memory per-key deque sliding window. This resets on server restart. For MainNet use Redis or a distributed store.

## Endpoints (v1)

1) POST /api/v1/search_and_purchase

Request body:
{
  "query": string,
  "max_price_usdc": float,
  "auto_approve": boolean,
  "buyer_wallet": string,
  "buyer_user_id": string | null
}

Response data on success:
{
  "insight_text": string,
  "listing_id": string,
  "seller_wallet": string,
  "price_paid_usdc": float,
  "payment_method": string,
  "tx_id": string | null,
  "session_id": string
}

2) GET /api/v1/listings

Query params: `min_reputation=0&max_price=10.0&limit=10&source_type=all&offset=0`

Response data on success:
{
  "listings": [ ... ],
  "total_count": int,
  "has_more": bool
}

3) GET /api/v1/sellers/{wallet}/reputation

Response data on success:
{
  "wallet": string,
  "effective_score": int,
  "raw_score": int,
  "total_purchases": int,
  "decay_info": { ... }
}

4) POST /api/v1/list_insight

Request body:
{
  "insight_text": string,
  "price_usdc": float,
  "seller_wallet": string,
  "seller_user_id": string | null
}

Response data on success:
{
  "listing_id": string,
  "tx_id": string,
  "ipfs_cid": string,
  "price_usdc": float
}

## Errors

- Use the envelope `error` object to convey machine-readable codes and human-friendly messages.
- Authentication errors:
  - `MISSING_API_KEY` -> HTTP 401
  - `INVALID_API_KEY` -> HTTP 403
- Rate limit:
  - `RATE_LIMIT_EXCEEDED` -> HTTP 429 with `Retry-After` and `X-RateLimit-*` headers

## Database tables (summary)

- `api_keys` (key_id, key_hash, owner_name, owner_email, tier, rate_limit_per_minute, created_at, last_used_at, total_requests, is_active)
- `api_request_log` (request_id, key_id, endpoint, method, request_body_summary, response_status, response_time_ms, requested_at, ip_address)

## Notes

- Use router-level dependencies (APIRouter(dependencies=[Depends(verify_api_key), Depends(check_rate_limit)])) so auth runs before rate limiting and before handlers.
- Use `request.state` to pass `api_key_record` from auth to rate limit and to handlers without re-querying the DB.
- The in-memory rate limiter is for demo/dev only. Replace with Redis for production to support multiple processes and persistence.
