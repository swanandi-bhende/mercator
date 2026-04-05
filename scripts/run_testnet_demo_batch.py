from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from datetime import datetime as dt
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ENV = {}
for raw in (ROOT / ".env").read_text().splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    ENV[key.strip()] = value.strip().strip('"').strip("'")

BASE = "http://127.0.0.1:8000"
SELLER = ENV["DEPLOYER_ADDRESS"]
BUYER = ENV["BUYER_WALLET"]

runs = [
    {
        "label": "run-1",
        "insight_text": "NIFTY moonbreak circuit resistance map at 24500 today",
        "price": 0.50,
        "query": "NIFTY moonbreak circuit resistance map insight",
    },
    {
        "label": "run-2",
        "insight_text": "BankNifty riverpivot rebound pulse anchored near 52000",
        "price": 0.75,
        "query": "riverpivot rebound pulse insight",
    },
    {
        "label": "run-3",
        "insight_text": "ITindex fogtrend decay signal with cautious guidance followthrough",
        "price": 0.25,
        "query": "fogtrend decay signal insight",
    },
    {
        "label": "run-4",
        "insight_text": "FMCG lanternflow defensive accumulation window ahead of results",
        "price": 1.00,
        "query": "lanternflow defensive accumulation insight",
    },
    {
        "label": "run-5",
        "insight_text": "Metals ironpulse shortcover glide into close on firm cues",
        "price": 0.40,
        "query": "ironpulse shortcover glide insight",
    },
]


def post_json(path: str, payload: dict[str, object]) -> dict[str, object]:
    request = Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def parse_escrow_tx(post_payment_output: object) -> str:
    if not isinstance(post_payment_output, str):
        return ""
    marker = "escrow="
    if marker in post_payment_output:
        return post_payment_output.split(marker, 1)[-1].split("\n", 1)[0].split(" |", 1)[0].strip()
    return ""


def extract_delivered_insight(post_payment_output: object) -> str:
    if not isinstance(post_payment_output, str):
        return ""
    marker = "Here is your human trading insight:"
    if marker not in post_payment_output:
        return ""
    tail = post_payment_output.split(marker, 1)[-1].strip()
    lines = [line for line in tail.splitlines() if line.strip()]
    if not lines:
        return ""
    # Stop before transaction id summary line when present.
    cleaned: list[str] = []
    for line in lines:
        if line.startswith("Transaction IDs:"):
            break
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def parse_log_timestamp(line: str) -> dt | None:
    try:
        ts = " ".join(line.split(" ")[:2]).rstrip(",")
        return dt.strptime(ts, "%Y-%m-%d %H:%M:%S,%f")
    except Exception:
        return None


def log_verification(payment_tx: str) -> tuple[bool, bool, float | None]:
    """Return (escrow_released, delivered, seconds_from_payment_confirm_to_delivery)."""
    log_path = ROOT / "demo_flow.log"
    if not log_path.exists() or not payment_tx:
        return False, False, None

    lines = log_path.read_text(errors="ignore").splitlines()
    confirm_idx = -1
    confirm_time = None
    for idx, line in enumerate(lines):
        if f"Payment confirmed | tx_id={payment_tx}" in line:
            confirm_idx = idx
            confirm_time = parse_log_timestamp(line)

    if confirm_idx < 0:
        return False, False, None

    escrow_released = False
    delivered = False
    delivery_time = None
    for line in lines[confirm_idx + 1 :]:
        if "Escrow redeem confirmed" in line:
            escrow_released = True
        if "IPFS content delivered" in line and delivery_time is None:
            delivered = True
            delivery_time = parse_log_timestamp(line)

    delay = None
    if confirm_time and delivery_time:
        delay = (delivery_time - confirm_time).total_seconds()
    return escrow_released, delivered, delay


ledger: list[dict[str, object]] = []
batch_tag = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
for index, run in enumerate(runs, start=1):
    run_started_at = datetime.now(timezone.utc).isoformat()
    unique_marker = f"BATCH_{batch_tag}_RUN_{index}"
    seller_text = f"{unique_marker}: {run['insight_text']}"
    query_text = f"{unique_marker} {run['query']}"

    listing_response = post_json(
        "/list",
        {
            "insight_text": seller_text,
            "price": run["price"],
            "seller_wallet": SELLER,
        },
    )

    demo_started = time.perf_counter()
    purchase_response = post_json(
        "/demo_purchase",
        {
            "user_query": query_text,
            "buyer_address": BUYER,
            "user_approval_input": "approve",
            "force_buy_for_test": True,
        },
    )
    elapsed_seconds = round(time.perf_counter() - demo_started, 3)

    result = as_dict(purchase_response.get("result", {}))
    payment_status_raw = result.get("payment_status", {})
    if isinstance(payment_status_raw, str):
        try:
            payment_status = json.loads(payment_status_raw)
        except Exception:
            payment_status = {}
    else:
        payment_status = as_dict(payment_status_raw)

    post_payment_output = payment_status.get("post_payment_output", "")
    final_insight = str(purchase_response.get("final_insight_text", "") or "")
    if not final_insight and isinstance(post_payment_output, str):
        final_insight = post_payment_output

    payment_tx = str(payment_status.get("transaction_id", "") or "")
    payment_url = str(payment_status.get("explorer_url", "") or "")
    payment_details = as_dict(payment_status.get("payment_details", {}))
    escrow_tx = parse_escrow_tx(post_payment_output)
    escrow_url = f"https://testnet.explorer.algorand.org/tx/{escrow_tx}" if escrow_tx else ""
    delivered_text = extract_delivered_insight(post_payment_output) or final_insight.strip()
    escrow_released, delivered_logged, confirm_to_delivery_seconds = log_verification(payment_tx)

    entry = {
        "run": index,
        "timestamp_utc": run_started_at,
        "seller_insight": seller_text,
        "query": query_text,
        "seller_upload_tx": listing_response.get("transaction_id") or listing_response.get("txId", ""),
        "seller_upload_url": listing_response.get("explorer_url", ""),
        "listing_id": listing_response.get("listing_id", ""),
        "asa_id": listing_response.get("asa_id", ""),
        "reasoning_summary": str(result.get("evaluation", "") or "")[:300],
        "selected_listing_id": payment_details.get("listing_id", ""),
        "selected_amount_usdc": payment_details.get("amount_usdc", ""),
        "payment_tx": payment_tx,
        "payment_url": payment_url,
        "escrow_tx": escrow_tx,
        "escrow_url": escrow_url,
        "final_delivered_insight_text": delivered_text,
        "delivered_matches_uploaded": delivered_text == seller_text,
        "escrow_released": escrow_released,
        "delivery_logged": delivered_logged,
        "confirm_to_delivery_seconds": confirm_to_delivery_seconds,
        "instant_access_after_payment": bool(confirm_to_delivery_seconds is not None and confirm_to_delivery_seconds <= 8.0),
        "elapsed_seconds": elapsed_seconds,
    }
    ledger.append(entry)
    print(json.dumps(entry, indent=2))

(ROOT / "testnet-demo-runs.raw.json").write_text(json.dumps(ledger, indent=2))
print("WROTE:testnet-demo-runs.raw.json")