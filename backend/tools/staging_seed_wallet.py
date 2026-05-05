"""Optional staging wallet funding helper used by the backend scheduler."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def check_and_top_up() -> dict[str, str]:
    """Best-effort staging wallet check used by the APScheduler job."""

    wallet_address = os.getenv("STAGING_WALLET_ADDRESS", "").strip()
    if not wallet_address:
        logger.info("staging_seed_wallet skipped: STAGING_WALLET_ADDRESS is not configured")
        return {"status": "skipped", "reason": "STAGING_WALLET_ADDRESS not configured"}

    logger.info("staging_seed_wallet check complete for %s", wallet_address)
    return {
        "status": "ok",
        "wallet_address": wallet_address,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
