from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen
import time

from algokit_utils import AlgorandClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.contracts.reputation.smart_contracts.artifacts.reputation.reputation_client import (  # noqa: E402
    ReputationClient,
)
from backend.utils.runtime_env import normalize_network_env  # noqa: E402


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key and value and not os.getenv(key):
            os.environ[key] = value.strip().strip('"').strip("'")


def _post_json(path: str, payload: dict[str, object]) -> dict[str, object]:
    request = Request(
        f"http://127.0.0.1:8000{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_reputation_client() -> ReputationClient:
    normalize_network_env()
    algorand = AlgorandClient.from_environment()

    deployer_mnemonic = os.getenv("DEPLOYER_MNEMONIC", "").strip()
    deployer_address = os.getenv("DEPLOYER_ADDRESS", "").strip()
    if deployer_mnemonic and deployer_address:
        signer = algorand.account.from_mnemonic(
            mnemonic=deployer_mnemonic,
            sender=deployer_address,
        )
        algorand.set_default_signer(signer)

    app_id = int(os.getenv("REPUTATION_APP_ID", "0"))
    if app_id <= 0:
        raise RuntimeError("REPUTATION_APP_ID is missing or invalid")

    return ReputationClient(
        algorand=algorand,
        app_id=app_id,
        default_sender=deployer_address or None,
    )


def _set_score_with_retry(seller: str, score: int, attempts: int = 4) -> None:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            client = _get_reputation_client()
            client.send.update_score((seller, score))
            return
        except Exception as err:  # noqa: BLE001
            last_error = err
            if attempt < attempts:
                time.sleep(0.7)
    raise RuntimeError(f"Failed to update reputation score after retries: {last_error}")


def main() -> None:
    _load_env()

    seller = os.getenv("DEPLOYER_ADDRESS", "").strip()
    buyer = os.getenv("BUYER_WALLET", "").strip()
    if not seller or not buyer:
        raise RuntimeError("DEPLOYER_ADDRESS and BUYER_WALLET must be configured")

    rep_client = _get_reputation_client()

    original_score_raw = rep_client.state.box.seller_scores.get_value(seller)
    original_score = int(original_score_raw) if original_score_raw is not None else 0

    low_score = 10
    query = "NIFTY moonbreak circuit resistance map"

    print(f"Original seller score: {original_score}")
    print(f"Setting temporary low score ({low_score}) for seller: {seller}")
    _set_score_with_retry(seller, low_score)

    updated_score_raw = rep_client.state.box.seller_scores.get_value(seller)
    updated_score = int(updated_score_raw) if updated_score_raw is not None else 0
    print(f"Updated seller score: {updated_score}")

    try:
        response = _post_json(
            "/demo_purchase",
            {
                "user_query": query,
                "buyer_address": buyer,
                "user_approval_input": "",
                "force_buy_for_test": False,
            },
        )
        print("Demo response:")
        print(json.dumps(response, indent=2))
    finally:
        print(f"Restoring seller score to: {original_score}")
        _set_score_with_retry(seller, original_score)
        verify_client = _get_reputation_client()
        restored_raw = verify_client.state.box.seller_scores.get_value(seller)
        restored = int(restored_raw) if restored_raw is not None else 0
        print(f"Restored seller score: {restored}")


if __name__ == "__main__":
    main()
