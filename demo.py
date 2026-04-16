from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import time
import warnings
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from algosdk.v2client import algod
from algosdk import account as algo_account
from algosdk import mnemonic as algo_mnemonic
from algosdk import transaction

warnings.filterwarnings(
    "ignore",
    message="Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.",
    category=UserWarning,
)

from backend.agent import run_agent
from backend.utils.runtime_env import configure_demo_logging, normalize_network_env


ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://127.0.0.1:3000"
SAMPLE_INSIGHT = "Sample trading insight: Buy NIFTY above 24500 with SL 24380"
SAMPLE_QUERY = "latest NIFTY 24500 call insight"
DEMO_LISTING_PRICE_USDC = float(os.getenv("DEMO_LISTING_PRICE_USDC", "0.05"))
USDC_ASA_ID = int(os.getenv("USDC_ASA_ID", "10458941") or 10458941)
KEEP_ALIVE = os.getenv("DEMO_KEEP_ALIVE", "").strip().lower() in {"1", "true", "yes", "on"}


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


def _build_algod_client() -> algod.AlgodClient:
    token = os.getenv("ALGOD_TOKEN", "")
    address = (
        os.getenv("ALGOD_URL", "").strip()
        or os.getenv("ALGOD_SERVER", "").strip()
        or "https://testnet-api.algonode.cloud"
    )
    return algod.AlgodClient(token, address)


def _asset_balance_micro(address: str, asset_id: int) -> int:
    if not address or asset_id <= 0:
        return 0
    try:
        account_info = _build_algod_client().account_info(address)
        assets = account_info.get("assets", [])
        holding = next((a for a in assets if int(a.get("asset-id", -1)) == asset_id), None)
        if not holding:
            return 0
        return int(holding.get("amount", 0) or 0)
    except Exception:
        return 0


def _algo_balance_micro(address: str) -> int:
    if not address:
        return 0
    try:
        return int(_build_algod_client().account_info(address).get("amount", 0) or 0)
    except Exception:
        return 0


def _send_algo(from_mnemonic: str, from_address: str, to_address: str, amount_micro: int) -> str:
    client = _build_algod_client()
    private_key = algo_mnemonic.to_private_key(from_mnemonic)
    derived = algo_account.address_from_private_key(private_key)
    if derived != from_address:
        raise RuntimeError(f"Mnemonic/address mismatch for sender {from_address}: derived {derived}")

    params = client.suggested_params()
    pay_txn = transaction.PaymentTxn(
        sender=from_address,
        sp=params,
        receiver=to_address,
        amt=int(amount_micro),
    )
    txid = client.send_transaction(pay_txn.sign(private_key))
    transaction.wait_for_confirmation(client, txid, 4)
    return txid


def _ensure_deployer_algo_for_listing(logger: logging.Logger, fallback_buyer_wallet: str) -> None:
    deployer_wallet = os.getenv("DEPLOYER_ADDRESS", "").strip()
    buyer_mnemonic = os.getenv("BUYER_MNEMONIC", "").strip()
    if not deployer_wallet:
        return

    # Keep a small safety margin over min-balance requirements for app funding + fees.
    required_micro = 1_200_000
    deployer_balance = _algo_balance_micro(deployer_wallet)
    if deployer_balance >= required_micro:
        return

    if not fallback_buyer_wallet or not buyer_mnemonic or fallback_buyer_wallet == deployer_wallet:
        raise RuntimeError(
            f"DEPLOYER_ADDRESS has low Algo balance ({deployer_balance}) and cannot be auto-funded."
        )

    topup_amount = (required_micro - deployer_balance) + 200_000
    buyer_algo = _algo_balance_micro(fallback_buyer_wallet)
    if buyer_algo <= topup_amount + 200_000:
        raise RuntimeError(
            f"Cannot top up deployer Algo from buyer wallet. buyer_algo={buyer_algo}, needed>{topup_amount}"
        )

    txid = _send_algo(
        from_mnemonic=buyer_mnemonic,
        from_address=fallback_buyer_wallet,
        to_address=deployer_wallet,
        amount_micro=topup_amount,
    )
    logger.info(
        "Auto-funded deployer for listing flow | from=%s to=%s amount_micro=%s tx=%s",
        fallback_buyer_wallet,
        deployer_wallet,
        topup_amount,
        txid,
    )


async def _run_demo_flow(logger: logging.Logger) -> str:
    normalize_network_env()
    seller_wallet = os.getenv("DEPLOYER_ADDRESS", "").strip() or os.getenv("BUYER_WALLET", "").strip()
    if not seller_wallet:
        raise RuntimeError("DEPLOYER_ADDRESS or BUYER_WALLET must be configured")

    configured_buyer = os.getenv("BUYER_WALLET", "").strip() or os.getenv("BUYER_ADDRESS", "").strip()
    deployer_wallet = os.getenv("DEPLOYER_ADDRESS", "").strip()
    buyer_wallet = configured_buyer

    _ensure_deployer_algo_for_listing(logger, configured_buyer)

    configured_buyer_balance = _asset_balance_micro(configured_buyer, USDC_ASA_ID)
    deployer_balance = _asset_balance_micro(deployer_wallet, USDC_ASA_ID)

    if configured_buyer_balance <= 0 and deployer_balance > 0:
        buyer_wallet = deployer_wallet
        logger.info("Configured buyer has no USDC; falling back to deployer wallet for demo purchase")

    selected_buyer_balance = _asset_balance_micro(buyer_wallet, USDC_ASA_ID)
    if selected_buyer_balance <= 0:
        raise RuntimeError(
            "No funded buyer wallet found for demo purchase. Fund BUYER_WALLET or DEPLOYER_ADDRESS with USDC."
        )

    # Keep listing price safely below live buyer balance so repeated demo runs remain stable.
    affordable_micro = max(1_000, selected_buyer_balance - 5_000)
    affordable_usdc = affordable_micro / 1_000_000
    effective_listing_price_usdc = min(DEMO_LISTING_PRICE_USDC, affordable_usdc)
    logger.info(
        "Demo pricing selected | buyer=%s buyer_usdc_micro=%s listing_price_usdc=%.6f",
        buyer_wallet,
        selected_buyer_balance,
        effective_listing_price_usdc,
    )

    logger.info("Submitting seller listing to /list")
    listing_response = await asyncio.to_thread(
        _post_json,
        f"{BACKEND_URL}/list",
        {
            "insight_text": SAMPLE_INSIGHT,
            "price": f"{effective_listing_price_usdc:.6f}",
            "seller_wallet": seller_wallet,
        },
        150,
        2,
    )

    logger.info("Seller upload complete")
    logger.info("On-chain ASA created")
    logger.info("Listing response: %s", listing_response)

    listing_id = int(listing_response.get("listing_id", 0) or 0)
    if listing_id <= 0:
        raise RuntimeError(f"Missing listing_id in /list response: {listing_response}")

    await asyncio.sleep(3)

    logger.info("Submitting buyer flow to /demo_purchase")
    purchase_response = await asyncio.to_thread(
        _post_json,
        f"{BACKEND_URL}/demo_purchase",
        {
            "user_query": SAMPLE_QUERY,
            "user_approval_input": "approve",
            "force_buy_for_test": True,
            "buyer_address": buyer_wallet,
            "target_listing_id": listing_id,
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
        if KEEP_ALIVE:
            logger.info("DEMO_KEEP_ALIVE is enabled; leaving backend and frontend running until interrupted.")
            while True:
                await asyncio.sleep(1)
    finally:
        _shutdown()


if __name__ == "__main__":
    asyncio.run(main())
