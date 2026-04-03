from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_repo_env_files() -> None:
    root = repo_root()
    load_dotenv(root / ".env", override=False)
    load_dotenv(root / ".env.testnet", override=False)


def normalize_network_env() -> None:
    load_repo_env_files()

    algod_url = os.getenv("ALGOD_URL", "").strip()
    indexer_url = os.getenv("INDEXER_URL", "").strip()

    if not os.getenv("ALGOD_SERVER") and algod_url:
        os.environ["ALGOD_SERVER"] = algod_url
    if not os.getenv("INDEXER_SERVER") and indexer_url:
        os.environ["INDEXER_SERVER"] = indexer_url
    if not os.getenv("ALGOD_PORT"):
        os.environ["ALGOD_PORT"] = "443"


def missing_required_env_keys() -> list[str]:
    required_keys = [
        "GEMINI_API_KEY",
        "PINATA_JWT",
        "INSIGHT_LISTING_APP_ID",
        "ESCROW_APP_ID",
        "REPUTATION_APP_ID",
        "DEPLOYER_MNEMONIC",
        "DEPLOYER_ADDRESS",
        "BUYER_WALLET",
        "BUYER_MNEMONIC",
        "USDC_ASA_ID",
    ]

    missing: list[str] = []
    for key in required_keys:
        if not os.getenv(key, "").strip():
            missing.append(key)

    if not (os.getenv("ALGOD_URL", "").strip() or os.getenv("ALGOD_SERVER", "").strip()):
        missing.append("ALGOD_URL/ALGOD_SERVER")
    if not (os.getenv("INDEXER_URL", "").strip() or os.getenv("INDEXER_SERVER", "").strip()):
        missing.append("INDEXER_URL/INDEXER_SERVER")

    return missing


def warn_missing_required_env(logger: logging.Logger | None = None) -> None:
    missing = missing_required_env_keys()
    if not missing:
        return

    message = "Missing required environment keys: " + ", ".join(missing)
    if logger is None:
        print(f"WARNING: {message}")
    else:
        logger.warning(message)