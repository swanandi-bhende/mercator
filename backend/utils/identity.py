from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Tuple

import algosdk.encoding as encoding
import algosdk.util as util
from algosdk import mnemonic


@dataclass
class AgentManifest:
    agent_name: str
    wallet: str
    role: str
    registered_at_round: int | None = None


def _manifest_payload(agent_name: str, wallet: str, role: str) -> bytes:
    return b"mercator:v1|" + agent_name.encode("utf-8") + b"|" + encoding.decode_address(wallet) + b"|" + role.encode("utf-8")


def generate_manifest(agent_name: str, wallet: str, role: str, private_key: str) -> Tuple[str, str]:
    # Construct manifest JSON with deterministic ordering and separators
    manifest_json = json.dumps(
        {"agent_name": agent_name, "wallet": wallet, "role": role}, separators=(",", ":"), sort_keys=True
    )

    signature_b64 = util.sign_bytes(_manifest_payload(agent_name, wallet, role), private_key)
    return manifest_json, signature_b64


def verify_manifest_locally(manifest_json: str, signature_b64: str, wallet: str) -> bool:
    try:
        parsed = json.loads(manifest_json)
        payload = _manifest_payload(parsed["agent_name"], parsed["wallet"], parsed["role"])
        return util.verify_bytes(payload, signature_b64, wallet)
    except Exception:
        return False


def private_key_from_mnemonic(mn: str) -> str:
    return mnemonic.to_private_key(mn)
