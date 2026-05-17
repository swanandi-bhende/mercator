# Purpose: Server-side custodial wallet generation and encrypted mnemonic storage for non-crypto user onboarding. Demo only — not for production use with real funds.
from __future__ import annotations

from dataclasses import dataclass
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidTag
import bcrypt
import subprocess
import secrets
import hashlib
import uuid
import time
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from algosdk import account, mnemonic as algo_mnemonic
from backend.utils.http_client import get_http_client
from .db import _connect, initialise_curator_schema
from .retry import retry_with_backoff

# Module-level constants
PBKDF2_ITERATIONS = 600_000
PBKDF2_SALT_LENGTH = 32
AES_KEY_LENGTH = 32
NONCE_LENGTH = 12
USDC_TESTNET_ASSET_ID = 10458941

logger = logging.getLogger(__name__)


_DEMO_SESSION_TTL = timedelta(hours=2)
_demo_sessions: dict[str, dict[str, object]] = {}


@dataclass
class CustodialWallet:
    user_id: str
    algo_address: str
    encrypted_mnemonic: str
    pbkdf2_salt: str
    password_hash: str


@dataclass
class WalletDecryptResult:
    success: bool
    mnemonic: str
    private_key: str
    error: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cleanup_expired_sessions() -> None:
    now = datetime.now(timezone.utc)
    expired = [
        user_id
        for user_id, session in _demo_sessions.items()
        if not isinstance(session.get("expires_at"), datetime) or session["expires_at"] <= now
    ]
    for user_id in expired:
        _demo_sessions.pop(user_id, None)


def create_demo_session(user_id: str, password: str) -> str:
    _cleanup_expired_sessions()
    token = secrets.token_urlsafe(24)
    _demo_sessions[user_id] = {
        "token": token,
        "password": password,
        "expires_at": datetime.now(timezone.utc) + _DEMO_SESSION_TTL,
    }
    return token


def validate_demo_session(user_id: str, session_token: str) -> bool:
    _cleanup_expired_sessions()
    session = _demo_sessions.get(user_id)
    if not session:
        return False
    return str(session.get("token", "")) == session_token


def get_session_password(user_id: str, session_token: str) -> str | None:
    if not validate_demo_session(user_id, session_token):
        return None
    session = _demo_sessions.get(user_id)
    if not session:
        return None
    return str(session.get("password", ""))


def generate_wallet(password: str) -> CustodialWallet:
    # Generate fresh Algorand account
    private_key, address = account.generate_account()
    mnemonic_phrase = algo_mnemonic.from_private_key(private_key)

    # Generate PBKDF2 salt and derive AES key
    salt = secrets.token_bytes(PBKDF2_SALT_LENGTH)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=AES_KEY_LENGTH,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
        backend=default_backend(),
    )
    key = kdf.derive(password.encode("utf-8"))

    # Encrypt mnemonic with AES-GCM
    nonce = secrets.token_bytes(NONCE_LENGTH)
    aesgcm = AESGCM(key)
    ciphertext_with_tag = aesgcm.encrypt(nonce, mnemonic_phrase.encode("utf-8"), None)
    ciphertext = ciphertext_with_tag[:-16]
    tag = ciphertext_with_tag[-16:]

    nonce_hex = nonce.hex()
    ciphertext_hex = ciphertext.hex()
    tag_hex = tag.hex()
    encrypted_mnemonic = f"{nonce_hex}:{ciphertext_hex}:{tag_hex}"

    # Hash password with bcrypt for authentication
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

    user_id_str = str(uuid.uuid4())

    return CustodialWallet(
        user_id=user_id_str,
        algo_address=address,
        encrypted_mnemonic=encrypted_mnemonic,
        pbkdf2_salt=salt.hex(),
        password_hash=password_hash,
    )


def decrypt_mnemonic(encrypted_mnemonic: str, pbkdf2_salt: str, password: str) -> WalletDecryptResult:
    try:
        parts = encrypted_mnemonic.split(":")
        if len(parts) != 3:
            return WalletDecryptResult(False, "", "", "Malformed encrypted_mnemonic format")
        nonce_hex, ciphertext_hex, tag_hex = parts
        nonce = bytes.fromhex(nonce_hex)
        ciphertext = bytes.fromhex(ciphertext_hex)
        tag = bytes.fromhex(tag_hex)

        salt = bytes.fromhex(pbkdf2_salt)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=AES_KEY_LENGTH,
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
            backend=default_backend(),
        )
        key = kdf.derive(password.encode("utf-8"))

        aesgcm = AESGCM(key)
        ciphertext_with_tag = ciphertext + tag
        plaintext = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
        mnemonic_phrase = plaintext.decode("utf-8")
        return WalletDecryptResult(True, mnemonic_phrase, "", "")
    except InvalidTag:
        return WalletDecryptResult(False, "", "", "Invalid password or corrupted wallet data")
    except Exception as exc:  # pragma: no cover - unexpected error path
        return WalletDecryptResult(False, "", "", f"Decryption failed: {exc}")


def create_user(email: str, password: str) -> tuple[CustodialWallet, str]:
    email_hash = hashlib.sha256(email.lower().strip().encode("utf-8")).hexdigest()
    initialise_curator_schema()
    conn = _connect()
    try:
        cur = conn.execute("SELECT user_id FROM users WHERE email_hash = ?", (email_hash,))
        row = cur.fetchone()
        if row:
            raise ValueError("An account with this email already exists")

        wallet = generate_wallet(password)

        conn.execute(
            """
            INSERT INTO users (
                user_id, email_hash, password_hash, algo_address,
                encrypted_mnemonic, pbkdf2_salt, created_at, onboarding_complete
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                wallet.user_id,
                email_hash,
                wallet.password_hash,
                wallet.algo_address,
                wallet.encrypted_mnemonic,
                wallet.pbkdf2_salt,
                _utc_now_iso(),
            ),
        )
        conn.commit()
        return wallet, wallet.user_id
    finally:
        conn.close()


def is_custodial_address(algo_address: str) -> bool:
    initialise_curator_schema()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT user_id FROM users WHERE algo_address = ?",
            (algo_address,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def get_user_id_by_address(algo_address: str) -> str | None:
    initialise_curator_schema()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT user_id FROM users WHERE algo_address = ?",
            (algo_address,),
        ).fetchone()
        if not row:
            return None
        return str(row["user_id"])
    finally:
        conn.close()


def _run_dispenser_fund(args: list[str]) -> str:
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        logger.error("AlgoKit dispenser call failed: %s", result.stderr.strip())
        raise RuntimeError(f"ALGO faucet funding failed: {result.stderr}")
    return result.stdout.strip()


def _parse_txid_from_output(output: str) -> str | None:
    tokens = output.replace("\n", " ").split(" ")
    for token in tokens:
        candidate = token.strip()
        if len(candidate) >= 40 and candidate.isalnum() and candidate.upper() == candidate:
            return candidate
    return None


async def _read_balances_from_indexer(algo_address: str) -> tuple[int, int]:
    client = await get_http_client()
    r = await client.get(f"https://testnet-idx.algonode.cloud/v2/accounts/{algo_address}", timeout=12)
    r.raise_for_status()
    payload = r.json()
    account_data = payload.get("account", {}) if isinstance(payload, dict) else {}

    algo_balance = int(account_data.get("amount", 0) or 0)
    usdc_balance = 0
    assets = account_data.get("assets", []) if isinstance(account_data, dict) else []
    if isinstance(assets, list):
        for item in assets:
            if not isinstance(item, dict):
                continue
            if int(item.get("asset-id", 0) or 0) == USDC_TESTNET_ASSET_ID:
                usdc_balance = int(item.get("amount", 0) or 0)
                break
    return algo_balance, usdc_balance


async def fund_new_wallet(algo_address: str) -> dict:
    funding_tx_ids: list[str] = []

    algo_output = retry_with_backoff(
        lambda: _run_dispenser_fund(
            [
                "algokit",
                "dispenser",
                "fund",
                "--receiver",
                algo_address,
                "--amount",
                "5000000",
                "--whole-units",
            ]
        ),
        max_attempts=3,
        delay_seconds=2,
    )
    algo_txid = _parse_txid_from_output(algo_output)
    if algo_txid:
        funding_tx_ids.append(algo_txid)

    usdc_output = retry_with_backoff(
        lambda: _run_dispenser_fund(
            [
                "algokit",
                "dispenser",
                "fund",
                "--receiver",
                algo_address,
                "--asset-id",
                str(USDC_TESTNET_ASSET_ID),
                "--amount",
                "2000000",
            ]
        ),
        max_attempts=3,
        delay_seconds=2,
    )
    usdc_txid = _parse_txid_from_output(usdc_output)
    if usdc_txid:
        funding_tx_ids.append(usdc_txid)

    deadline = time.time() + 15
    algo_balance = 0
    usdc_balance = 0
    while time.time() < deadline:
        try:
            algo_balance, usdc_balance = await _read_balances_from_indexer(algo_address)
            if algo_balance >= 4_000_000 and usdc_balance >= 1_000_000:
                return {
                    "algo_funded": True,
                    "usdc_funded": True,
                    "algo_balance": algo_balance,
                    "usdc_balance": usdc_balance,
                    "funding_tx_ids": funding_tx_ids,
                    "funding_confirmed": True,
                }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Balance confirmation poll failed for %s: %s", algo_address, exc)
        await asyncio.sleep(2)

    return {
        "algo_funded": True,
        "usdc_funded": True,
        "algo_balance": algo_balance,
        "usdc_balance": usdc_balance,
        "funding_tx_ids": funding_tx_ids,
        "funding_confirmed": False,
    }


def authenticate_user(email: str, password: str) -> tuple[bool, str, str]:
    email_hash = hashlib.sha256(email.lower().strip().encode("utf-8")).hexdigest()
    initialise_curator_schema()
    conn = _connect()
    try:
        cur = conn.execute(
            "SELECT user_id, password_hash, algo_address FROM users WHERE email_hash = ?",
            (email_hash,),
        )
        row = cur.fetchone()
        if not row:
            return False, "", ""
        stored_hash = row["password_hash"]
        user_id = row["user_id"]
        algo_addr = row["algo_address"]
        if bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8")):
            return True, user_id, algo_addr
        return False, "", ""
    finally:
        conn.close()


def get_wallet_for_user(user_id: str, password: str) -> WalletDecryptResult:
    initialise_curator_schema()
    conn = _connect()
    try:
        cur = conn.execute(
            "SELECT encrypted_mnemonic, pbkdf2_salt FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return WalletDecryptResult(False, "", "", "User not found")

        encrypted_mnemonic = row["encrypted_mnemonic"]
        salt_hex = row["pbkdf2_salt"]
        decrypt_result = decrypt_mnemonic(encrypted_mnemonic, salt_hex, password)
        if not decrypt_result.success:
            return decrypt_result

        # Convert mnemonic back to private_key string (same format as account.generate_account())
        private_key = algo_mnemonic.to_private_key(decrypt_result.mnemonic)
        return WalletDecryptResult(True, decrypt_result.mnemonic, private_key, "")
    finally:
        conn.close()
