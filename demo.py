from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from backend.agent import run_agent
from backend.utils.runtime_env import configure_demo_logging, normalize_network_env


ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://127.0.0.1:3000"
SAMPLE_INSIGHT = "Sample trading insight: Buy NIFTY above 24500 with SL 24380"
SAMPLE_QUERY = "latest NIFTY 24500 call insight"


def _launch(command: list[str], cwd: Path) -> subprocess.Popen[str]:
    return subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=sys.stdout,
        stderr=sys.stderr,
        text=True,
    )


def _post_json(url: str, payload: dict[str, object], timeout_seconds: int = 120, max_attempts: int = 3) -> dict[str, object]:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (TimeoutError, URLError) as err:
            last_error = err
            if attempt >= max_attempts:
                break
            time.sleep(min(5, attempt * 2))
    raise RuntimeError(f"POST {url} failed after {max_attempts} attempts: {last_error}")


def _get_json(url: str) -> dict[str, object]:
    with urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def _ping_url(url: str) -> None:
    with urlopen(url, timeout=5) as response:
        response.read(1)


async def _wait_for_http(url: str, timeout_seconds: int = 60) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            await asyncio.to_thread(_get_json, url)
            return
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
            await asyncio.sleep(1)
    raise RuntimeError(f"Timed out waiting for {url}")


async def _wait_for_url(url: str, timeout_seconds: int = 60) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            await asyncio.to_thread(_ping_url, url)
            return
        except (HTTPError, URLError, TimeoutError, OSError):
            await asyncio.sleep(1)
    raise RuntimeError(f"Timed out waiting for {url}")


async def _run_demo_flow(logger: logging.Logger) -> str:
    normalize_network_env()
    seller_wallet = os.getenv("DEPLOYER_ADDRESS", "").strip() or os.getenv("BUYER_WALLET", "").strip()
    if not seller_wallet:
        raise RuntimeError("DEPLOYER_ADDRESS or BUYER_WALLET must be configured")

    logger.info("Submitting seller listing to /list")
    listing_response = await asyncio.to_thread(
        _post_json,
        f"{BACKEND_URL}/list",
        {
            "insight_text": SAMPLE_INSIGHT,
            "price": "1.00",
            "seller_wallet": seller_wallet,
        },
        150,
        2,
    )

    logger.info("Seller upload complete")
    logger.info("On-chain ASA created")
    logger.info("Listing response: %s", listing_response)

    await asyncio.sleep(3)

    logger.info("Submitting buyer flow to /demo_purchase")
    purchase_response = await asyncio.to_thread(
        _post_json,
        f"{BACKEND_URL}/demo_purchase",
        {
            "user_query": SAMPLE_QUERY,
            "user_approval_input": "approve",
            "force_buy_for_test": True,
            "buyer_address": os.getenv("BUYER_WALLET", "").strip() or os.getenv("BUYER_ADDRESS", "").strip(),
        },
        360,
        2,
    )

    result = purchase_response.get("result", {}) if isinstance(purchase_response, dict) else {}
    final_insight = purchase_response.get("final_insight_text", "") if isinstance(purchase_response, dict) else ""
    if not final_insight and isinstance(result, dict):
        payment_status = result.get("payment_status", {})
        if isinstance(payment_status, dict):
            post_payment_output = payment_status.get("post_payment_output", "")
            if isinstance(post_payment_output, str):
                final_insight = post_payment_output

    logger.info("Buyer flow result: %s", purchase_response)
    print("\nFinal delivered insight:\n")
    print(final_insight)
    return str(final_insight)


async def main() -> None:
    normalize_network_env()
    demo_logger = configure_demo_logging()
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("mercator.demo")
    logger.setLevel(logging.INFO)

    backend_proc = _launch([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"], ROOT)
    frontend_proc = _launch(["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "3000"], FRONTEND)

    def _shutdown(*_: object) -> None:
        for proc in (backend_proc, frontend_proc):
            if proc.poll() is None:
                proc.terminate()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        await _wait_for_http(f"{BACKEND_URL}/health")
        await _wait_for_url(FRONTEND_URL)
        demo_logger.info("Demo servers ready")
        await _run_demo_flow(logger)
    finally:
        _shutdown()


if __name__ == "__main__":
    asyncio.run(main())
