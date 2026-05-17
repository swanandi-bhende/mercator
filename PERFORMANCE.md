Performance Baseline
===================

Collected with `scripts/profile_endpoints.py` (n=10 sequential requests).

Cold run (server restarted before run):

- `/health`: p50=1.1225 ms, p90=3.0924 ms, p99=9.5534 ms, mean=2.3040 ms
- `/api/v1/listings`: p50=0.9330 ms, p90=1.2395 ms, p99=2.3999 ms, mean=1.1632 ms
- `/sellers/{wallet}/reputation`: p50=0.9474 ms, p90=1.2113 ms, p99=1.5138 ms, mean=1.0840 ms
- `/sellers/{wallet}/profile`: p50=0.9243 ms, p90=1.2408 ms, p99=1.3238 ms, mean=1.0449 ms
- `/api/v1/search_and_purchase` (short query): p50=1.1299 ms, p90=1.3602 ms, p99=1.9940 ms, mean=1.2870 ms
- `/curator/status`: p50=3.5860 ms, p90=5.0568 ms, p99=5.2886 ms, mean=4.2962 ms
- `/traces/latest`: p50=1.6024 ms, p90=1.9631 ms, p99=2.0108 ms, mean=1.7650 ms
- `/fee_config`: p50=188.7358 ms, p90=225.5426 ms, p99=262.2667 ms, mean=208.4261 ms

Warm run (immediately after cold run):

- `/health`: p50=1.0610 ms, p90=1.3825 ms, p99=1.5654 ms, mean=1.2121 ms
- `/api/v1/listings`: p50=0.8633 ms, p90=0.9699 ms, p99=1.0036 ms, mean=0.9301 ms
- `/sellers/{wallet}/reputation`: p50=0.8737 ms, p90=1.0490 ms, p99=1.0558 ms, mean=0.9460 ms
- `/sellers/{wallet}/profile`: p50=0.8279 ms, p90=0.9667 ms, p99=1.1573 ms, mean=0.9057 ms
- `/api/v1/search_and_purchase` (short query): p50=1.0021 ms, p90=1.1536 ms, p99=1.1705 ms, mean=1.0786 ms
- `/curator/status`: p50=2.9964 ms, p90=3.6860 ms, p99=3.7203 ms, mean=3.3336 ms
- `/traces/latest`: p50=1.4189 ms, p90=2.1602 ms, p99=4.1689 ms, mean=1.8763 ms
- `/fee_config`: p50=192.5981 ms, p90=218.0331 ms, p99=219.9457 ms, mean=205.9934 ms

Top three endpoints by baseline P90 (warm-run):
1. `/curator/status` — 3686 ms
2. `/traces/latest` — 2160 ms
3. `/fee_config` — 218 ms

Notes:
- `curator/status` and `/traces/latest` are the largest warm P90s and are primary optimisation targets (likely I/O-heavy or DB queries).
- `/fee_config` has a consistently high P90 (~200ms) and should be optimised for reduced third-party calls or added caching.

Next steps (planned):
- Create a shared `httpx.AsyncClient` and migrate HTTP calls to it.
- Wrap synchronous `algod` / `indexer` calls using `asyncio.to_thread` and expose async wrappers.
- Add `cachetools.TTLCache` to hotspot functions and add cache invalidation where listings change.
