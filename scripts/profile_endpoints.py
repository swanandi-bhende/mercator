"""
Profile selected endpoints and write baseline latencies to JSON.
Usage:
  pip install httpx
  python3 scripts/profile_endpoints.py --base-url http://localhost:8000 --known-wallet <WALLET> --n 10

The script will prompt you to prepare a cold server run (restart server),
then perform a warm run immediately after.
"""

import argparse
import asyncio
import httpx
import json
import time
import statistics
from pathlib import Path
from typing import Optional, Dict, Any, List


def percentile(sorted_list: List[float], p: float) -> float:
    if not sorted_list:
        return 0.0
    k = (len(sorted_list) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_list):
        return float(sorted_list[-1])
    d0 = sorted_list[f] * (c - k)
    d1 = sorted_list[c] * (k - f)
    return float(d0 + d1)


async def profile_endpoint(client: httpx.AsyncClient, method: str, path: str, body: Optional[Dict[str, Any]] = None, n: int = 10) -> Dict[str, Any]:
    elapsed_ms = []
    for i in range(n):
        start = time.perf_counter()
        if method.upper() == "GET":
            r = await client.get(path)
        else:
            r = await client.request(method.upper(), path, json=body)
        end = time.perf_counter()
        elapsed_ms.append((end - start) * 1000.0)
    elapsed_ms.sort()
    result = {
        "path": path,
        "method": method.upper(),
        "p50_ms": percentile(elapsed_ms, 50),
        "p90_ms": percentile(elapsed_ms, 90),
        "p99_ms": percentile(elapsed_ms, 99),
        "min_ms": min(elapsed_ms) if elapsed_ms else 0.0,
        "max_ms": max(elapsed_ms) if elapsed_ms else 0.0,
        "mean_ms": statistics.mean(elapsed_ms) if elapsed_ms else 0.0,
        "samples": elapsed_ms,
    }
    return result


async def run_profile(base_url: str, known_wallet: str, n: int, cold_out: Path, warm_out: Path):
    endpoints = [
        ("GET", "/health", None),
        ("GET", "/api/v1/listings", None),
        ("GET", f"/sellers/{known_wallet}/reputation", None),
        ("GET", f"/sellers/{known_wallet}/profile", None),
        ("POST", "/api/v1/search_and_purchase", {"query": "test", "auto_approve": False}),
        ("GET", "/curator/status", None),
        ("GET", "/traces/latest", None),
        ("GET", "/fee_config", None),
    ]

    async with httpx.AsyncClient(base_url=base_url, timeout=httpx.Timeout(10.0)) as client:
        print("Prepare for COLD run: restart server now if you want a true cold cache.")
        input("Press Enter to start the cold run when ready...")
        cold_results = []
        for method, path, body in endpoints:
            print(f"Profiling (cold) {method} {path} ...")
            r = await profile_endpoint(client, method, path, body, n=n)
            cold_results.append(r)
        cold_out.parent.mkdir(parents=True, exist_ok=True)
        cold_out.write_text(json.dumps(cold_results, indent=2))
        print(f"Wrote cold results to {cold_out}")

        print("Starting WARM run (no restart) immediately after cold run.")
        warm_results = []
        for method, path, body in endpoints:
            print(f"Profiling (warm) {method} {path} ...")
            r = await profile_endpoint(client, method, path, body, n=n)
            warm_results.append(r)
        warm_out.write_text(json.dumps(warm_results, indent=2))
        print(f"Wrote warm results to {warm_out}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="http://localhost:8000", help="Base URL of the server")
    p.add_argument("--known-wallet", required=True, help="Known wallet address to profile seller endpoints")
    p.add_argument("--n", type=int, default=10, help="Number of sequential requests per endpoint")
    p.add_argument("--cold-output", default="scripts/baseline_latencies_cold.json")
    p.add_argument("--warm-output", default="scripts/baseline_latencies_warm.json")
    args = p.parse_args()

    asyncio.run(run_profile(args.base_url, args.known_wallet, args.n, Path(args.cold_output), Path(args.warm_output)))


if __name__ == "__main__":
    main()
