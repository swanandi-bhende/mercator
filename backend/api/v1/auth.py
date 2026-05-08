from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.utils import db as _db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect():
    return _db._connect()


def generate_api_key(owner_name: str, owner_email: str, tier: str = "developer", plaintext_key: Optional[str] = None) -> tuple[str, str]:
    """Generate and store a new API key. Returns (plaintext_key, key_id).

    The plaintext key is returned only at generation time and is not stored.
    """
    if plaintext_key is None:
        plaintext = f"mercator_{secrets.token_hex(24)}"
    else:
        plaintext = plaintext_key

    # Ensure DB schema exists before insertion
    _db.initialise_curator_schema()

    key_id = str(uuid.uuid4())
    key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    rate_limits = {"demo": 10, "developer": 60, "enterprise": 600}
    rate = rate_limits.get(tier, 60)
    created_at = _now_iso()

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO api_keys (
                key_id, key_hash, owner_name, owner_email, tier, rate_limit_per_minute, created_at, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (key_id, key_hash, owner_name, owner_email, tier, rate, created_at),
        )
        conn.commit()

    return plaintext, key_id


def lookup_api_key(plaintext_key: str) -> Optional[Dict[str, Any]]:
    """Look up an API key record by plaintext key (header-provided key).

    Returns a dict of the row if found and active, otherwise None.
    """
    key_hash = hashlib.sha256(plaintext_key.encode()).hexdigest()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM api_keys WHERE key_hash = ? AND is_active = 1",
            (key_hash,),
        ).fetchone()
    return dict(row) if row else None


def update_last_used(key_id: str) -> None:
    """Update last_used_at and increment total_requests for a key."""
    now = _now_iso()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE api_keys
            SET last_used_at = ?, total_requests = COALESCE(total_requests, 0) + 1
            WHERE key_id = ?
            """,
            (now, key_id),
        )
        conn.commit()


def seed_demo_key() -> None:
    """Ensure the Mercator demo key exists (hardcoded plaintext).

    This is the key published in the README for judges to test.
    """
    demo_owner = "Mercator Demo"
    # Ensure tables exist
    _db.initialise_curator_schema()

    with _connect() as conn:
        exists = conn.execute(
            "SELECT 1 FROM api_keys WHERE owner_name = ?",
            (demo_owner,),
        ).fetchone()
    if exists:
        return

    # Insert the known demo key value
    plaintext = "mercator_demo_key_algobharat_round3"
    generate_api_key(demo_owner, "demo@mercator.io", "demo", plaintext_key=plaintext)
