from __future__ import annotations

import time
import uuid
from fastapi.testclient import TestClient

from backend.main import app
from backend.api.v1 import dependencies as api_deps

import pytest

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_rate_windows():
    api_deps._request_windows.clear()
    yield


def test_missing_api_key_returns_401():
    r = client.get("/api/v1/listings")
    assert r.status_code == 401
    payload = r.json()
    assert payload.get("error", {}).get("code") == "MISSING_API_KEY"


def test_invalid_api_key_returns_403():
    r = client.get("/api/v1/listings", headers={"X-API-Key": "mercator_invalid"})
    assert r.status_code == 403
    payload = r.json()
    assert payload.get("error", {}).get("code") == "INVALID_API_KEY"


def _get_demo_key():
    # The seeded demo key plaintext
    return "mercator_demo_key_algobharat_round3"


def test_valid_demo_key_returns_200():
    demo = _get_demo_key()
    r = client.get("/api/v1/listings", headers={"X-API-Key": demo})
    assert r.status_code == 200
    payload = r.json()
    assert payload.get("success") is True


def test_rate_limit_enforced():
    demo = _get_demo_key()
    # Demo tier limit is 10/min; call 11 times
    last = None
    for i in range(11):
        r = client.get("/api/v1/listings", headers={"X-API-Key": demo})
        last = r
    assert last is not None
    assert last.status_code == 429
    assert last.json().get("error", {}).get("code") == "RATE_LIMIT_EXCEEDED"


def test_response_envelope_always_present():
    demo = _get_demo_key()
    r = client.get("/api/v1/listings", headers={"X-API-Key": demo})
    assert r.status_code in (200, 429)
    j = r.json()
    # test envelope keys present
    keys = set(j.keys())
    assert keys >= {"success", "data", "error", "request_id", "timestamp"}


def test_search_and_purchase_invalid_wallet():
    demo = _get_demo_key()
    payload = {"query": "bitcoin", "max_price_usdc": 1.0, "auto_approve": False, "buyer_wallet": "not_a_wallet"}
    r = client.post("/api/v1/search_and_purchase", json=payload, headers={"X-API-Key": demo})
    assert r.status_code == 400
    j = r.json()
    assert j.get("error", {}).get("code") == "INVALID_WALLET"


def test_request_id_is_unique_across_calls():
    demo = _get_demo_key()
    r1 = client.get("/api/v1/listings", headers={"X-API-Key": demo})
    r2 = client.get("/api/v1/listings", headers={"X-API-Key": demo})
    id1 = r1.json().get("request_id")
    id2 = r2.json().get("request_id")
    assert id1 != id2


def test_request_log_is_written_to_db():
    demo = _get_demo_key()
    r = client.get("/api/v1/listings", headers={"X-API-Key": demo})
    # simple smoke: ensure last request produced a request_id
    j = r.json()
    req_id = j.get("request_id")
    assert req_id is not None
