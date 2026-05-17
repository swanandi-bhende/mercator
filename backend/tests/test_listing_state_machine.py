from __future__ import annotations

import pytest


class FakeInsightListingClient:
    def __init__(self, default_expiry_rounds: int = 17280, start_round: int = 1000):
        self._listings: dict[int, dict] = {}
        self._default = int(default_expiry_rounds)
        self.current_round = int(start_round)

    def create_listing(self, price_micro_usdc: int, ipfs_cid: str, source_type: str, custom_expiry_rounds: int = 0):
        expiry_rounds = custom_expiry_rounds if custom_expiry_rounds > 0 else self._default
        expiry_round = self.current_round + expiry_rounds
        lid = max(self._listings.keys(), default=0) + 1
        rec = {
            "listing_id": lid,
            "seller_wallet": "SOMESELLER",
            "price_micro_usdc": int(price_micro_usdc),
            "ipfs_cid": ipfs_cid,
            "source_type": source_type,
            "state": "active",
            "created_round": self.current_round,
            "expiry_round": expiry_round,
            "sold_at_round": 0,
            "buyer_wallet": None,
            "expired_at_round": 0,
            "subscription_purchase_count": 0,
        }
        self._listings[lid] = rec
        return lid

    def call_get_listing_state(self, listing_id: int):
        rec = self._listings.get(listing_id)
        if rec is None:
            raise RuntimeError("Listing not found")
        return rec["state"]

    # contract-like send methods (may raise AssertionError with exact messages)
    def send_mark_sold(self, listing_id: int, buyer: str):
        rec = self._listings.get(listing_id)
        if rec is None:
            raise AssertionError("Listing not found")
        if rec["state"] != "active":
            raise AssertionError("Listing not in ACTIVE state")
        if self.current_round > rec["expiry_round"]:
            raise AssertionError("Listing has expired — purchase window closed")
        rec["state"] = "sold"
        rec["buyer_wallet"] = buyer
        rec["sold_at_round"] = self.current_round

    def send_mark_sold_to_subscriber(self, listing_id: int, buyer: str):
        rec = self._listings.get(listing_id)
        if rec is None:
            raise AssertionError("Listing not found")
        if rec["state"] != "active":
            raise AssertionError("Listing not in ACTIVE state")
        if self.current_round > rec["expiry_round"]:
            raise AssertionError("Listing has expired — purchase window closed")
        rec["subscription_purchase_count"] += 1

    def send_check_and_expire(self, listing_id: int):
        rec = self._listings.get(listing_id)
        if rec is None:
            raise AssertionError("Listing not found")
        if rec["state"] != "active":
            return
        if self.current_round <= rec["expiry_round"]:
            return
        rec["state"] = "expired"
        rec["expired_at_round"] = self.current_round


@pytest.fixture
def listing_client():
    return FakeInsightListingClient(default_expiry_rounds=17280, start_round=1000)


def test_create_listing_sets_active_state(listing_client):
    lid = listing_client.create_listing(1_000_000, "QmCID", "human")
    state = listing_client.call_get_listing_state(lid)
    assert state == "active"
    rec = listing_client._listings[lid]
    assert rec["expiry_round"] == listing_client.current_round + 17280


def test_create_listing_with_custom_expiry(listing_client):
    lid = listing_client.create_listing(1_000_000, "QmCID", "human", custom_expiry_rounds=1000)
    rec = listing_client._listings[lid]
    assert rec["expiry_round"] == listing_client.current_round + 1000


def test_mark_sold_transitions_to_sold(listing_client):
    lid = listing_client.create_listing(1_000_000, "QmCID", "human")
    listing_client.send_mark_sold(lid, "BUYER1")
    rec = listing_client._listings[lid]
    assert rec["state"] == "sold"
    assert rec["buyer_wallet"] == "BUYER1"
    assert rec["sold_at_round"] == listing_client.current_round


def test_mark_sold_on_expired_listing_reverts(listing_client):
    lid = listing_client.create_listing(1_000_000, "QmCID", "human", custom_expiry_rounds=1)
    listing_client.current_round += 5
    with pytest.raises(AssertionError) as exc:
        listing_client.send_mark_sold(lid, "BUYER2")
    assert "expired" in str(exc.value)


def test_double_sale_reverts(listing_client):
    lid = listing_client.create_listing(1_000_000, "QmCID", "human")
    listing_client.send_mark_sold(lid, "BUYER1")
    with pytest.raises(AssertionError) as exc:
        listing_client.send_mark_sold(lid, "BUYER2")
    assert "not in ACTIVE" in str(exc.value)


def test_check_and_expire_transitions_to_expired(listing_client):
    lid = listing_client.create_listing(1_000_000, "QmCID", "human", custom_expiry_rounds=1)
    listing_client.current_round += 2
    listing_client.send_check_and_expire(lid)
    rec = listing_client._listings[lid]
    assert rec["state"] == "expired"
    assert rec["expired_at_round"] == listing_client.current_round


def test_check_and_expire_on_active_listing_is_noop(listing_client):
    lid = listing_client.create_listing(1_000_000, "QmCID", "human", custom_expiry_rounds=100)
    listing_client.send_check_and_expire(lid)
    rec = listing_client._listings[lid]
    assert rec["state"] == "active"


def test_subscription_purchase_does_not_change_state_to_sold(listing_client):
    lid = listing_client.create_listing(1_000_000, "QmCID", "human")
    listing_client.send_mark_sold_to_subscriber(lid, "SUB1")
    rec = listing_client._listings[lid]
    assert rec["state"] == "active"
    assert rec["subscription_purchase_count"] == 1


def test_get_active_listings_excludes_expired_and_sold(listing_client):
    a = listing_client.create_listing(1_000_000, "QmA", "human")
    b = listing_client.create_listing(1_000_000, "QmB", "human")
    c = listing_client.create_listing(1_000_000, "QmC", "human")
    # mark b sold
    listing_client.send_mark_sold(b, "BUYERX")
    # expire c
    listing_client._listings[c]["expiry_round"] = listing_client.current_round - 1
    listing_client.send_check_and_expire(c)

    active_ids = [lid for lid, rec in listing_client._listings.items() if rec["state"] == "active"]
    assert a in active_ids and b not in active_ids and c not in active_ids
