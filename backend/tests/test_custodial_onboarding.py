from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from backend import main as main_module
from backend.utils import custodial_wallet as wallet_module
from backend.utils.db import initialise_curator_schema


@pytest.fixture
def isolated_db(monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory) -> None:
    db_path = tmp_path / "custodial_onboarding_test.db"
    monkeypatch.setenv("CURATOR_DB_PATH", str(db_path))
    initialise_curator_schema()


def test_generate_wallet_produces_valid_algorand_address(isolated_db: None) -> None:
    wallet = wallet_module.generate_wallet("testpassword123")
    assert len(wallet.algo_address) == 58
    assert re.match(r"^[A-Z2-7]", wallet.algo_address) is not None


def test_encryption_decryption_round_trip(isolated_db: None) -> None:
    wallet = wallet_module.generate_wallet("mypassword99")
    result = wallet_module.decrypt_mnemonic(wallet.encrypted_mnemonic, wallet.pbkdf2_salt, "mypassword99")
    assert result.success is True
    assert len(result.mnemonic.split()) == 25


def test_wrong_password_returns_failure(isolated_db: None) -> None:
    wallet = wallet_module.generate_wallet("mypassword99")
    result = wallet_module.decrypt_mnemonic(wallet.encrypted_mnemonic, wallet.pbkdf2_salt, "badpassword88")
    assert result.success is False
    assert "Invalid" in result.error


def test_duplicate_email_raises_error(isolated_db: None) -> None:
    wallet_module.create_user("dupe@example.com", "mypassword99")
    with pytest.raises(ValueError):
        wallet_module.create_user("dupe@example.com", "mypassword99")


def test_onboard_endpoint_returns_wallet_address(isolated_db: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        main_module,
        "fund_new_wallet",
        lambda _address: {
            "algo_funded": True,
            "usdc_funded": True,
            "algo_balance": 5_000_000,
            "usdc_balance": 2_000_000,
            "funding_tx_ids": ["TX1", "TX2"],
            "funding_confirmed": True,
        },
    )

    with TestClient(main_module.app) as client:
        response = client.post(
            "/onboard",
            json={
                "display_name": "Demo User",
                "email": "demo_user@example.com",
                "password": "StrongPass123",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload.get("algo_address")


def test_login_wrong_password_returns_401(isolated_db: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "fund_new_wallet", lambda _address: {"funding_confirmed": False, "algo_balance": 0, "usdc_balance": 0, "funding_tx_ids": []})

    wallet_module.create_user("login_user@example.com", "StrongPass123")
    with TestClient(main_module.app) as client:
        response = client.post(
            "/auth/login",
            json={
                "email": "login_user@example.com",
                "password": "WrongPass123",
            },
        )

    assert response.status_code == 401


def test_export_endpoint_returns_mnemonic(isolated_db: None) -> None:
    _, user_id = wallet_module.create_user("export_user@example.com", "StrongPass123")
    with TestClient(main_module.app) as client:
        response = client.post(
            "/wallet/export",
            json={
                "user_id": user_id,
                "password": "StrongPass123",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload.get("mnemonic", "").split()) == 25


def test_export_endpoint_wrong_password_returns_error(isolated_db: None) -> None:
    _, user_id = wallet_module.create_user("export_bad_user@example.com", "StrongPass123")
    with TestClient(main_module.app) as client:
        response = client.post(
            "/wallet/export",
            json={
                "user_id": user_id,
                "password": "WrongPass123",
            },
        )

    assert response.status_code in {400, 401}
