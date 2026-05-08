"""Retry helpers for transient network and CLI operations."""

from __future__ import annotations

import time
from typing import Callable, TypeVar


T = TypeVar("T")


def retry_with_backoff(
    operation: Callable[[], T],
    *,
    max_attempts: int = 3,
    delay_seconds: float = 2.0,
) -> T:
    """Retry a callable with fixed backoff delays between attempts."""
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= max_attempts:
                break
            time.sleep(delay_seconds)
    if last_error is not None:
        raise last_error
    raise RuntimeError("retry_with_backoff failed without capturing an exception")
