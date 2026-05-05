from __future__ import annotations

import os
from dataclasses import dataclass


AUTO_MIN_RELEVANCE = int(os.getenv("AUTO_MIN_RELEVANCE", "85"))
AUTO_MIN_REPUTATION = int(os.getenv("AUTO_MIN_REPUTATION", "70"))
AUTO_MAX_PRICE_USDC = float(os.getenv("AUTO_MAX_PRICE_USDC", "0.30"))

if not 0 <= AUTO_MIN_RELEVANCE <= 100:
    raise ValueError("AUTO_MIN_RELEVANCE must be between 0 and 100")
if not 0 <= AUTO_MIN_REPUTATION <= 100:
    raise ValueError("AUTO_MIN_REPUTATION must be between 0 and 100")
if not 0.01 <= AUTO_MAX_PRICE_USDC <= 10.0:
    raise ValueError("AUTO_MAX_PRICE_USDC must be between 0.01 and 10.0")


@dataclass
class AutoApprovalResult:
    approved: bool
    relevance_passed: bool
    reputation_passed: bool
    price_passed: bool
    relevance_score: int
    reputation_score: int
    price_usdc: float
    thresholds_used: dict[str, float | int]
    rejection_reason: str


def check_auto_conditions(relevance_score: int, reputation_score: int, price_usdc: float) -> AutoApprovalResult:
    relevance_passed = relevance_score >= AUTO_MIN_RELEVANCE
    reputation_passed = reputation_score >= AUTO_MIN_REPUTATION
    price_passed = price_usdc <= AUTO_MAX_PRICE_USDC

    thresholds_used: dict[str, float | int] = {
        "AUTO_MIN_RELEVANCE": AUTO_MIN_RELEVANCE,
        "AUTO_MIN_REPUTATION": AUTO_MIN_REPUTATION,
        "AUTO_MAX_PRICE_USDC": AUTO_MAX_PRICE_USDC,
    }

    if relevance_passed and reputation_passed and price_passed:
        return AutoApprovalResult(
            approved=True,
            relevance_passed=True,
            reputation_passed=True,
            price_passed=True,
            relevance_score=relevance_score,
            reputation_score=reputation_score,
            price_usdc=price_usdc,
            thresholds_used=thresholds_used,
            rejection_reason="",
        )

    rejection_parts: list[str] = []
    if not relevance_passed:
        rejection_parts.append(
            f"Relevance {relevance_score} below threshold {AUTO_MIN_RELEVANCE}."
        )
    if not reputation_passed:
        rejection_parts.append(
            f"Reputation {reputation_score} below threshold {AUTO_MIN_REPUTATION}."
        )
    if not price_passed:
        rejection_parts.append(
            f"Price {price_usdc} USDC exceeds maximum {AUTO_MAX_PRICE_USDC} USDC."
        )

    rejection_reason = " ".join(rejection_parts).strip().rstrip(". ")
    return AutoApprovalResult(
        approved=False,
        relevance_passed=relevance_passed,
        reputation_passed=reputation_passed,
        price_passed=price_passed,
        relevance_score=relevance_score,
        reputation_score=reputation_score,
        price_usdc=price_usdc,
        thresholds_used=thresholds_used,
        rejection_reason=rejection_reason,
    )