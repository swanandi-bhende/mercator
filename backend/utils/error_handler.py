"""Centralized user-facing error helpers for backend flows.

Purpose: Map internal exceptions into consistent, UI-safe messages for IPFS, contract,
reputation, and x402 payment stages in the micropayment flow.
"""

from __future__ import annotations

import logging


def _log(logger: logging.Logger | None, code: str, details: str | None = None) -> None:
    """Emit structured error telemetry for user-facing backend failures.

    Inputs:
    - logger: Optional logger instance (falls back to module logger when missing).
    - code: Stable error category key.
    - details: Optional raw detail text.

    Output:
    - None. Writes a single normalized log line.

    Micropayment role:
    - Common sink for IPFS, contract, and x402 error signal logging used by API/tool layers.
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    suffix = f" | details={details}" if details else ""
    logger.error("%s%s", code, suffix)


def payment_rejected(logger: logging.Logger | None = None, details: str | None = None) -> str:
    """Build user-safe message for rejected x402 payment attempts.

    Inputs: optional logger and raw payment rejection details.
    Output: human-readable rejection message for API responses.
    Micropayment role: returned when simulation/submission rejects transfer.
    """
    _log(logger, "payment_rejected", details)
    return "Payment was rejected by x402 - please check your wallet balance"


def ipfs_down(logger: logging.Logger | None = None, details: str | None = None) -> str:
    """Build user-safe message for IPFS/pinning outages.

    Inputs: optional logger and underlying transport/service detail.
    Output: retry-friendly outage message string.
    Micropayment role: used when listing upload or post-payment content fetch fails.
    """
    _log(logger, "ipfs_down", details)
    return "IPFS downtime - please retry"


def contract_error(logger: logging.Logger | None = None, details: str | None = None) -> str:
    """Build user-safe message for smart-contract lookup/invoke failures.

    Inputs: optional logger and contract failure detail.
    Output: normalized contract error message string.
    Micropayment role: used across listing, escrow release, and listing fetch failures.
    """
    _log(logger, "contract_error", details)
    return "Contract error: listing not found or already redeemed"


def low_reputation(logger: logging.Logger | None = None, details: str | None = None) -> str:
    """Build message for trust-gate SKIP decisions.

    Inputs: optional logger and reputation context detail.
    Output: user-facing SKIP rationale string.
    Micropayment role: surfaced when agent blocks BUY due to seller score threshold.
    """
    _log(logger, "low_reputation", details)
    return "Insight was skipped because seller reputation is below threshold"


def insufficient_balance(logger: logging.Logger | None = None, details: str | None = None) -> str:
    """Build message for buyer-balance failures during x402 simulation/execution.

    Inputs: optional logger and low-balance detail text.
    Output: user-facing insufficient funds message.
    Micropayment role: returned on payment simulation underflow/overspend conditions.
    """
    _log(logger, "insufficient_balance", details)
    return "Payment was rejected by x402 - please check your wallet balance"
