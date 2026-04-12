"""Centralized user-facing error helpers for backend flows.

Purpose: Map internal exceptions into consistent, UI-safe messages for IPFS, contract,
reputation, and x402 payment stages in the micropayment flow.
"""

from __future__ import annotations

import logging


def _log(logger: logging.Logger | None, code: str, details: str | None = None) -> None:
    if logger is None:
        logger = logging.getLogger(__name__)
    suffix = f" | details={details}" if details else ""
    logger.error("%s%s", code, suffix)


def payment_rejected(logger: logging.Logger | None = None, details: str | None = None) -> str:
    _log(logger, "payment_rejected", details)
    return "Payment was rejected by x402 - please check your wallet balance"


def ipfs_down(logger: logging.Logger | None = None, details: str | None = None) -> str:
    _log(logger, "ipfs_down", details)
    return "IPFS downtime - please retry"


def contract_error(logger: logging.Logger | None = None, details: str | None = None) -> str:
    _log(logger, "contract_error", details)
    return "Contract error: listing not found or already redeemed"


def low_reputation(logger: logging.Logger | None = None, details: str | None = None) -> str:
    _log(logger, "low_reputation", details)
    return "Insight was skipped because seller reputation is below threshold"


def insufficient_balance(logger: logging.Logger | None = None, details: str | None = None) -> str:
    _log(logger, "insufficient_balance", details)
    return "Payment was rejected by x402 - please check your wallet balance"
