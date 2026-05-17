from __future__ import annotations

import asyncio
from typing import Dict, List
import logging

logger = logging.getLogger("mercator.failure_simulator")

# Central in-memory simulator flags for injected failure scenarios.
_SCENARIOS: Dict[str, bool] = {
    "ipfs_down": False,
    "algorand_timeout": False,
    "gemini_rate_limit": False,
    "insufficient_balance": False,
    "listing_expired": False,
    "unregistered_agent": False,
    "malformed_json": False,
    "payment_rejected": False,
    "reputation_too_low": False,
    "subscription_expired": False,
    "database_error": False,
    "x402_rejected": False,
}


def list_scenarios() -> List[str]:
    return list(_SCENARIOS.keys())


def is_active(scenario: str) -> bool:
    return bool(_SCENARIOS.get(scenario, False))


def active_scenarios() -> List[str]:
    return [k for k, v in _SCENARIOS.items() if v]


def _reset_scenario(scenario: str) -> None:
    if scenario in _SCENARIOS:
        _SCENARIOS[scenario] = False
        logger.info("Failure simulator: reset scenario %s", scenario)


async def _delayed_reset(scenario: str, delay_seconds: int) -> None:
    try:
        await asyncio.sleep(delay_seconds)
        _reset_scenario(scenario)
    except Exception:
        logger.exception("Error resetting simulated failure %s", scenario)


def trigger_scenario(scenario: str, duration_seconds: int = 10) -> bool:
    """Activate a simulated failure scenario for a short duration.

    Returns True if scenario was recognized and activated.
    """
    if scenario not in _SCENARIOS:
        return False
    _SCENARIOS[scenario] = True
    logger.warning("Failure simulator: triggered %s for %s seconds", scenario, duration_seconds)
    try:
        # Schedule asynchronous reset without awaiting
        asyncio.create_task(_delayed_reset(scenario, duration_seconds))
    except RuntimeError:
        # If not running inside an event loop (e.g., during import-time tests), fallback to synchronous reset
        loop = None
        try:
            loop = asyncio.get_event_loop()
        except Exception:
            pass
        if loop and loop.is_running():
            asyncio.create_task(_delayed_reset(scenario, duration_seconds))
        else:
            # best-effort: schedule using loop.call_later when possible
            try:
                loop.call_later(duration_seconds, _reset_scenario, scenario)  # type: ignore[attr-defined]
            except Exception:
                # Last resort: synchronous sleep (blocking) — avoid in production
                import time

                time.sleep(duration_seconds)
                _reset_scenario(scenario)
    return True
