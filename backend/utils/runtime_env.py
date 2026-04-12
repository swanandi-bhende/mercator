"""Runtime environment normalization and logging utilities.

Purpose: Load .env/.env.testnet, normalize algod/indexer variables, and provide
shared demo logging helpers used across backend API, tools, and tests.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv


def repo_root() -> Path:
    """Resolve repository root path.

    Input: none.
    Output: absolute Path to repository root.
    Micropayment role: anchors .env/.env.testnet and shared log file resolution.
    """
    return Path(__file__).resolve().parents[2]


def load_repo_env_files() -> None:
    """Load environment variables from repository env files.

    Input: none (reads .env and .env.testnet from repo root).
    Output: none (mutates process environment).
    Micropayment role: ensures backend/tools/contracts share consistent network keys.
    """
    root = repo_root()
    load_dotenv(root / ".env", override=False)
    testnet_values = dotenv_values(root / ".env.testnet")
    for key, value in testnet_values.items():
        if value is None:
            continue
        if not str(value).strip():
            continue
        os.environ[key] = str(value)


def normalize_network_env() -> None:
    """Normalize Algorand client env aliases for SDK compatibility.

    Input: none.
    Output: none (populates ALGOD_SERVER, INDEXER_SERVER, ALGOD_PORT when missing).
    Micropayment role: guarantees algod/indexer clients work across demo, API, and tools.
    """
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
    """Return missing mandatory environment keys for end-to-end flow.

    Input: none (reads current process env).
    Output: list of missing key names.
    Micropayment role: preflight validation before listing/search/payment paths run.
    """
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
    """Log a warning when required env configuration is incomplete.

    Input: optional logger.
    Output: none.
    Micropayment role: startup guardrail so operators catch config gaps before live demos.
    """
    missing = missing_required_env_keys()
    if not missing:
        return

    message = "Missing required environment keys: " + ", ".join(missing)
    if logger is None:
        print(f"WARNING: {message}")
    else:
        logger.warning(message)


def configure_demo_logging() -> logging.Logger:
    """Configure a shared file logger for the integrated demo flow."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    log_path = repo_root() / "demo_flow.log"
    has_file_handler = any(
        isinstance(handler, logging.FileHandler)
        and Path(getattr(handler, "baseFilename", "")) == log_path
        for handler in root_logger.handlers
    )
    if not has_file_handler:
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        root_logger.addHandler(file_handler)

    return logging.getLogger("demo.flow")