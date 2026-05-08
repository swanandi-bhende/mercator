"""Reputation contract: On-chain seller reputation scoring system.

This implementation follows the repository CONTRACTS.md design:
- Capped per-seller purchase history (sliding window of 20 entries) stored in a Box
- Raw scores are accumulated at purchase time and decay is applied dynamically
  in read-only getters to avoid constant writes.

Notes:
- `record_purchase` is intended to be invoked only as an inner call from the
  Escrow contract; it checks `Global.caller_app_id` against the configured
  `escrow_app_id` to enforce this.
- Purchase history is stored as a fixed-size StaticArray[20] and a `history_count`
  tracks how many entries are valid (0..20). When full, older entries are
  shifted left to make room for the newest purchase.
"""

from typing import Literal

from algopy import ARC4Contract, arc4, GlobalState, BoxMap, Global, Txn, op


class PurchaseRecord(arc4.Struct):
    buyer_address: arc4.Address
    listing_id: arc4.UInt64
    purchase_round: arc4.UInt64


class SellerRecord(arc4.Struct):
    raw_score: arc4.UInt64
    last_purchase_round: arc4.UInt64
    total_purchases: arc4.UInt64
    history_count: arc4.UInt64
    purchase_history: arc4.StaticArray[PurchaseRecord, Literal[20]]


class Reputation(ARC4Contract):
    owner = GlobalState(arc4.Address)
    escrow_app_id = GlobalState(arc4.UInt64)
    points_per_purchase = GlobalState(arc4.UInt64, default=arc4.UInt64(5))
    decay_threshold_rounds = GlobalState(arc4.UInt64, default=arc4.UInt64(30000))
    decay_rate_rounds = GlobalState(arc4.UInt64, default=arc4.UInt64(10000))
    min_score = GlobalState(arc4.UInt64, default=arc4.UInt64(0))
    total_sellers_tracked = GlobalState(arc4.UInt64, default=arc4.UInt64(0))

    seller_records = BoxMap(arc4.Address, SellerRecord, key_prefix=b"rep_")

    def __init__(self, escrow_id: arc4.UInt64, points: arc4.UInt64) -> None:
        # Basic constructor validation
        assert 1 <= points.native <= 50, "points_per_purchase must be 1..50"
        # Set deployer as owner
        self.owner.value = Txn.sender
        self.escrow_app_id.value = escrow_id
        self.points_per_purchase.value = points

    @arc4.abimethod()
    def record_purchase(self, seller: arc4.Address, buyer: arc4.Address, listing_id: arc4.UInt64) -> None:
        # Guard: only the configured Escrow app may record purchases (inner call)
        assert Global.caller_app_id == self.escrow_app_id.value.native, "Only the Escrow contract can record purchases"

        now_round = Global.round()

        # Check if SellerRecord exists
        exists = False
        try:
            exists = self.seller_records[seller].exists
        except Exception:
            exists = False

        points = self.points_per_purchase.value

        if not exists:
            # Create new SellerRecord with one history entry
            pr = PurchaseRecord(buyer_address=buyer, listing_id=listing_id, purchase_round=arc4.UInt64(now_round))
            history = [arc4.StaticDefault(PurchaseRecord) for _ in range(20)]
            history[0] = pr
            rec = SellerRecord(
                raw_score=points,
                last_purchase_round=arc4.UInt64(now_round),
                total_purchases=arc4.UInt64(1),
                history_count=arc4.UInt64(1),
                purchase_history=arc4.StaticArray(history),
            )
            self.seller_records[seller] = rec
            # Increment total sellers tracked
            self.total_sellers_tracked.value = arc4.UInt64(self.total_sellers_tracked.value.native + 1)
        else:
            # Read, update, and write back (sliding window)
            rec = self.seller_records.get(seller)
            # Update numeric fields
            rec.raw_score = arc4.UInt64(rec.raw_score.native + points.native)
            rec.last_purchase_round = arc4.UInt64(now_round)
            rec.total_purchases = arc4.UInt64(rec.total_purchases.native + 1)

            hc = rec.history_count.native
            if hc < 20:
                # place at index hc
                rec.purchase_history[hc] = PurchaseRecord(buyer_address=buyer, listing_id=listing_id, purchase_round=arc4.UInt64(now_round))
                rec.history_count = arc4.UInt64(hc + 1)
            else:
                # shift left and append at index 19
                for i in range(19):
                    rec.purchase_history[i] = rec.purchase_history[i + 1]
                rec.purchase_history[19] = PurchaseRecord(buyer_address=buyer, listing_id=listing_id, purchase_round=arc4.UInt64(now_round))

            # Write back
            self.seller_records[seller] = rec

        # Emit compact log: seller, new_raw_score, total_purchases
        try:
            raw = rec.raw_score.native
            tp = rec.total_purchases.native
            op.log(f"record_purchase|{seller}|{raw}|{tp}".encode())
        except Exception:
            op.log(b"record_purchase|log_failed")

    @arc4.abimethod(readonly=True)
    def get_score(self, seller: arc4.Address) -> arc4.UInt64:
        # Return 0 for unknown sellers
        try:
            exists = self.seller_records[seller].exists
        except Exception:
            exists = False
        if not exists:
            return arc4.UInt64(0)

        rec = self.seller_records.get(seller)
        raw_score = rec.raw_score.native
        last_round = rec.last_purchase_round.native

        current_round = Global.round()
        # Handle test/reset environments where current_round < last_round
        if current_round < last_round:
            return arc4.UInt64(raw_score)

        rounds_since = current_round - last_round
        threshold = self.decay_threshold_rounds.value.native
        if rounds_since <= threshold:
            return arc4.UInt64(raw_score)

        decay_rate = self.decay_rate_rounds.value.native
        decay_points = (rounds_since - threshold) // decay_rate

        if decay_points >= raw_score:
            return arc4.UInt64(self.min_score.value.native)
        return arc4.UInt64(raw_score - decay_points)

    @arc4.abimethod(readonly=True)
    def get_full_record(self, seller: arc4.Address) -> SellerRecord:
        try:
            exists = self.seller_records[seller].exists
        except Exception:
            exists = False
        if not exists:
            # zeroed SellerRecord
            history = [arc4.StaticDefault(PurchaseRecord) for _ in range(20)]
            return SellerRecord(raw_score=arc4.UInt64(0), last_purchase_round=arc4.UInt64(0), total_purchases=arc4.UInt64(0), history_count=arc4.UInt64(0), purchase_history=arc4.StaticArray(history))
        return self.seller_records.get(seller)

    @arc4.abimethod(readonly=True)
    def get_effective_score_with_breakdown(self, seller: arc4.Address) -> tuple:
        # returns (effective_score, raw_score, decay_points_applied, rounds_since_last_purchase, rounds_until_decay_starts)
        try:
            exists = self.seller_records[seller].exists
        except Exception:
            exists = False
        if not exists:
            return (arc4.UInt64(0), arc4.UInt64(0), arc4.UInt64(0), arc4.UInt64(0), arc4.UInt64(self.decay_threshold_rounds.value.native))

        rec = self.seller_records.get(seller)
        raw = rec.raw_score.native
        last_round = rec.last_purchase_round.native
        current_round = Global.round()
        if current_round < last_round:
            return (arc4.UInt64(raw), arc4.UInt64(raw), arc4.UInt64(0), arc4.UInt64(0), arc4.UInt64(self.decay_threshold_rounds.value.native))

        rounds_since = current_round - last_round
        threshold = self.decay_threshold_rounds.value.native
        if rounds_since <= threshold:
            return (arc4.UInt64(raw), arc4.UInt64(raw), arc4.UInt64(0), arc4.UInt64(rounds_since), arc4.UInt64(threshold - rounds_since))

        decay_rate = self.decay_rate_rounds.value.native
        decay_points = (rounds_since - threshold) // decay_rate
        effective = raw - decay_points if decay_points < raw else self.min_score.value.native
        rounds_until_decay_starts = 0
        return (arc4.UInt64(effective), arc4.UInt64(raw), arc4.UInt64(decay_points), arc4.UInt64(rounds_since), arc4.UInt64(rounds_until_decay_starts))

