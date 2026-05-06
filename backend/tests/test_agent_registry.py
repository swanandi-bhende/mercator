"""Unit tests for off-chain AgentRegistry identity helpers."""

import json

from algosdk import mnemonic
from algosdk.account import generate_account

from backend.utils.identity import generate_manifest, verify_manifest_locally, private_key_from_mnemonic


class TestManifestGeneration:
    """Test off-chain manifest generation and verification."""

    def test_generate_manifest_produces_valid_json(self):
        secret_key, address = generate_account()
        manifest_json, _ = generate_manifest("Test Agent", address, "curator", secret_key)

        data = json.loads(manifest_json)
        assert data["agent_name"] == "Test Agent"
        assert data["wallet"] == address
        assert data["role"] == "curator"

    def test_generate_manifest_uses_deterministic_json_encoding(self):
        secret_key, address = generate_account()
        agent_name = "Test Agent"

        manifest_1, _ = generate_manifest(agent_name, address, "buyer", secret_key)
        manifest_2, _ = generate_manifest(agent_name, address, "buyer", secret_key)

        assert manifest_1 == manifest_2

    def test_verify_manifest_locally_succeeds_with_correct_key(self):
        secret_key, address = generate_account()
        manifest_json, sig_b64 = generate_manifest("Test Agent", address, "curator", secret_key)

        assert verify_manifest_locally(manifest_json, sig_b64, address) is True

    def test_verify_manifest_locally_fails_with_wrong_key(self):
        secret_key_1, address_1 = generate_account()
        _, address_2 = generate_account()

        manifest_json, sig_b64 = generate_manifest("Test Agent", address_1, "curator", secret_key_1)

        assert verify_manifest_locally(manifest_json, sig_b64, address_2) is False

    def test_verify_manifest_locally_fails_with_tampered_json(self):
        secret_key, address = generate_account()
        manifest_json, sig_b64 = generate_manifest("Test Agent", address, "curator", secret_key)

        tampered = json.loads(manifest_json)
        tampered["role"] = "buyer"
        tampered_json = json.dumps(tampered, separators=(",", ":"), sort_keys=True)

        assert verify_manifest_locally(tampered_json, sig_b64, address) is False

    def test_verify_manifest_locally_returns_false_on_bad_base64(self):
        _, address = generate_account()
        manifest_json = '{"agent_name":"Test","role":"curator","wallet":"' + address + '"}'

        assert verify_manifest_locally(manifest_json, "not-valid-base64!", address) is False

    def test_private_key_from_mnemonic(self):
        secret_key, address = generate_account()
        phrase = mnemonic.from_private_key(secret_key)

        derived_private_key = private_key_from_mnemonic(phrase)

        msg = b"test message"
        from algosdk.util import sign_bytes, verify_bytes

        sig_1 = sign_bytes(msg, secret_key)
        sig_2 = sign_bytes(msg, derived_private_key)

        assert verify_bytes(msg, sig_1, address)
        assert verify_bytes(msg, sig_2, address)
