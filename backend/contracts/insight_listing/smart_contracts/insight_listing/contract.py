"""InsightListing smart contract: Creates and manages on-chain trading insight listings.

Purpose: The primary registry for all insights in the Mercator x402 platform.
Each listing entry stores: seller address, price (micro-USDC), IPFS CID, associated ASA ID.

Key Responsibilities:
1. create_listing(price, seller, ipfs_hash): Allocate new listing ID, mint linked ASA, store metadata.
2. next_listing_id: Sequential counter for unique listing IDs (global state).
3. listings: box map (listing_id => Listing struct) storing all listing metadata.

Contract Flow in Micropayment Cycle:
1. Seller calls create_listing\u2192 get listing_id + asa_id.
2. Buyer's agent calls semantic_search \u2192 fetches from InsightListing state.
3. Agent calls trigger_x402_payment (x402 transfer USDC to seller).
4. Buyer calls Escrow.release_after_payment to unlock content access.
5. Buyer receives IPFS content (seller retains ASA manager control for future proof).
"""

from typing import Literal, cast

from algopy import ARC4Contract, BoxMap, UInt64, arc4, itxn, GlobalState, Bytes, Global, Txn, op, urange


# Module-level state constants (string form for ARC-4 `String` fields)
STATE_ACTIVE = "active"
STATE_SOLD = "sold"
STATE_EXPIRED = "expired"


class ListingRecord(arc4.Struct):
    """On-chain metadata for a single listing, extended for state machine use.

    Fields required by the state machine:
      - seller_wallet, price_micro_usdc, ipfs_cid, source_type
      - state (arc4.String), created_round, expiry_round
      - sold_at_round, buyer_wallet, expired_at_round
      - subscription_purchase_count
    """
    seller_wallet: arc4.Address
    price_micro_usdc: arc4.UInt64
    ipfs_cid: arc4.String
    source_type: arc4.String
    state: arc4.String
    created_round: arc4.UInt64
    expiry_round: arc4.UInt64
    sold_at_round: arc4.UInt64
    buyer_wallet: arc4.Address
    expired_at_round: arc4.UInt64
    subscription_purchase_count: arc4.UInt64


class ListingSummary(arc4.Struct):
    """Compact summary for listing search results (cheap to return)."""
    listing_id: arc4.UInt64
    seller_wallet: arc4.Address
    price_micro_usdc: arc4.UInt64
    expiry_round: arc4.UInt64
    source_type: arc4.String
    state: arc4.String


class InsightListing(ARC4Contract):
    """On-chain listing registry for trading insights with state-machine semantics."""

    # App references
    registry_app_id: GlobalState[arc4.UInt64]
    escrow_app_id: GlobalState[arc4.UInt64]
    reputation_app_id: GlobalState[arc4.UInt64]

    # Configurable default expiry rounds (set at deploy-time via constructor)
    default_expiry_rounds: GlobalState[arc4.UInt64]

    # Marketplace health counters
    total_active_listings: GlobalState[arc4.UInt64]
    total_sold_listings: GlobalState[arc4.UInt64]
    total_expired_listings: GlobalState[arc4.UInt64]

    # Box maps
    listings: BoxMap[UInt64, ListingRecord]
    subscriber_purchases: BoxMap[UInt64, arc4.StaticArray[arc4.Address, Literal[100]]]

    def __init__(self) -> None:
        # Initialize GlobalState holders and BoxMaps (follow patterns used elsewhere in repo)
        self.registry_app_id = GlobalState(arc4.UInt64)
        self.escrow_app_id = GlobalState(arc4.UInt64)
        self.reputation_app_id = GlobalState(arc4.UInt64)

        self.default_expiry_rounds = GlobalState(arc4.UInt64)
        self.total_active_listings = GlobalState(arc4.UInt64)
        self.total_sold_listings = GlobalState(arc4.UInt64)
        self.total_expired_listings = GlobalState(arc4.UInt64)

        self.listings = BoxMap(UInt64, ListingRecord, key_prefix=b"listing_")
        self.subscriber_purchases = BoxMap(UInt64, arc4.StaticArray[arc4.Address, Literal[100]], key_prefix=b"subp_")

        # Set deployment-time default expiry value (default ~3 days)
        self.default_expiry_rounds.value = arc4.UInt64(17280)

    @arc4.abimethod()
    def create_listing(
        self,
        price_micro_usdc: arc4.UInt64,
        ipfs_cid: arc4.String,
        source_type: arc4.String,
        custom_expiry_rounds: arc4.UInt64,
    ) -> UInt64:
        """Publish a new trading insight and receive seller ASA for proof-of-ownership.
        
        Purpose: Allocate unique listing ID and link IPFS content permanently on-chain.
        
        Actions:
        1. Verify seller is registered in AgentRegistry before proceeding (cross-contract call).
        2. Increment next_listing_id counter \u2192 allocate new listing ID.
        3. Call itxn.AssetConfig to mint one ASA with:
           - INSIGHT token name, Mercator Insight asset name, IpfsHash as URL.
           - Seller as manager + reserve + freeze + clawback (seller controls proof token).
           - Fee=1000 micro-Algo.
        4. Store Listing struct in boxes: {price, seller, ipfs_hash, asa_id}.
        5. Increment counter for next invocation.
        6. Call AgentRegistry.increment_transaction_count to record seller activity.
        7. Return listing_id to caller (frontend caches this).
        
        Args:
            price: Settlement amount (micro-USDC). e.g., 5_000_000 = 5 USDC.
            seller: Seller's Algorand wallet (58-char checksummed address).
            ipfs_hash: Content CID (e.g., \"Qm...\") pinned on Pinata.
        
        Returns:
            listing_id: Unique identifier (used in /discover results, x402 payment, escrow).
        
        Raises:
            AssertionError if seller is not registered in AgentRegistry.
        """
        # Guards (exact messages required by spec)
        # AgentRegistry registration check
        if self.registry_app_id.value.native != 0:
            is_registered, registration_check_txn = arc4.abi_call[arc4.Bool](
                "is_registered(address)bool",
                Txn.sender,
                app_id=self.registry_app_id.value.native,
            )
            assert is_registered, "Unregistered agent — call AgentRegistry.register() first"

        assert price_micro_usdc.native > 0, "Price must be greater than zero"
        assert ipfs_cid.native.bytes.length >= 46, "IPFS CID must be at least 46 characters"
        assert source_type == "curator_agent" or source_type == "human", "source_type must be curator_agent or human"

        # Determine expiry rounds
        expiry_rounds = custom_expiry_rounds.native if custom_expiry_rounds.native > 0 else self.default_expiry_rounds.value.native
        assert expiry_rounds <= 1_000_000, "Expiry cannot exceed 1,000,000 rounds (~115 days)"

        # Use confirmation round inside contract
        now_round = Global.round
        expiry_round = arc4.UInt64(now_round + expiry_rounds)

        # Deterministic listing_id: sha256(Txn.sender || itob(now_round)) -> first 8 bytes -> btoi -> UInt64
        digest = op.sha256(op.concat(Txn.sender, op.itob(now_round)))
        first8 = op.substring(digest, 0, 8)
        listing_id = op.btoi(first8)

        # Create and write ListingRecord
        rec = ListingRecord(
            seller_wallet=arc4.Address(Txn.sender),
            price_micro_usdc=price_micro_usdc,
            ipfs_cid=ipfs_cid,
            source_type=source_type,
            state=arc4.String(STATE_ACTIVE),
            created_round=arc4.UInt64(now_round),
            expiry_round=expiry_round,
            sold_at_round=arc4.UInt64(0),
            buyer_wallet=arc4.Address(Bytes(b"\x00" * 32)),
            expired_at_round=arc4.UInt64(0),
            subscription_purchase_count=arc4.UInt64(0),
        )

        self.listings[listing_id] = rec.copy()
        # Update counters
        self.total_active_listings.value = arc4.UInt64(self.total_active_listings.value.native + 1)

        # Emit compact ListingCreated log
        arc4.emit("ListingCreated", listing_id, arc4.Address(Txn.sender), expiry_round, source_type)

        return listing_id

    @arc4.abimethod(readonly=True)
    def get_listing_state(self, listing_id: UInt64) -> arc4.String:
        exists = self.listings.maybe(listing_id)[1]
        if not exists:
            return arc4.String("missing")
        rec = self.listings[listing_id].copy()
        return rec.state

    @arc4.abimethod(readonly=True)
    def get_seller(self, listing_id: UInt64) -> arc4.Address:
        exists = self.listings.maybe(listing_id)[1]
        assert exists, "Listing not found"
        return self.listings[listing_id].copy().seller_wallet

    @arc4.abimethod(readonly=True)
    def get_active_listings(self, listing_ids: arc4.DynamicArray[UInt64]) -> arc4.DynamicArray[ListingSummary]:
        """Return compact summaries for the provided listing IDs.

        Note: This method does not enumerate Boxes. The backend should query
        the indexer for candidate listing_ids and call this method with a
        bounded array of IDs to fetch summaries cheaply.
        """
        out = arc4.DynamicArray[ListingSummary]()
        for lid in listing_ids:
            exists = self.listings.maybe(lid)[1]
            if not exists:
                # Skip missing listings
                continue
            rec = self.listings[lid].copy()
            summary = ListingSummary(
                listing_id=lid,
                seller_wallet=rec.seller_wallet,
                price_micro_usdc=rec.price_micro_usdc,
                expiry_round=rec.expiry_round,
                source_type=rec.source_type,
                state=rec.state,
            )
            out.append(summary)
        return out

    @arc4.abimethod()
    def mark_sold_to_subscriber(self, listing_id: UInt64, buyer: arc4.Address) -> None:
        exists = self.listings.maybe(listing_id)[1]
        assert exists, "Listing not found"
        rec = self.listings[listing_id].copy()
        # Guard: must be active
        assert rec.state.native == STATE_ACTIVE, "Listing not in ACTIVE state"
        # Guard: not expired
        assert rec.expiry_round.native >= Global.round, "Listing has expired — purchase window closed"

        # Update subscriber_purchases box (initialize if needed)
        sl_exists = self.subscriber_purchases.maybe(listing_id)[1]
        if not sl_exists:
            zero_addr = arc4.Address(Bytes(b"\x00" * 32))
            sl = arc4.StaticArray[arc4.Address, Literal[100]](
                zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr,
                zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr,
                zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr,
                zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr,
                zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr,
                zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr,
                zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr,
                zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr,
                zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr,
                zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr, zero_addr,
            )
            sl[0] = buyer
            self.subscriber_purchases[listing_id] = sl.copy()
            rec.subscription_purchase_count = arc4.UInt64(1)
        else:
            sl = self.subscriber_purchases[listing_id].copy()
            idx = rec.subscription_purchase_count.native
            if idx < 100:
                sl[idx] = buyer
                rec.subscription_purchase_count = arc4.UInt64(idx + 1)
                self.subscriber_purchases[listing_id] = sl.copy()

        # write back listing record (state remains ACTIVE)
        self.listings[listing_id] = rec.copy()
        arc4.emit("ListingSubscriberPurchase", listing_id, buyer, arc4.UInt64(Global.round))

    @arc4.abimethod()
    def mark_sold(self, listing_id: UInt64, buyer: arc4.Address) -> None:
        # Escrow-only guard
        assert Global.caller_application_id == self.escrow_app_id.value.native, "Only Escrow can mark a listing as sold"

        exists = self.listings.maybe(listing_id)[1]
        assert exists, "Listing not found"
        rec = self.listings[listing_id].copy()
        assert rec.state.native == STATE_ACTIVE, "Listing not in ACTIVE state"
        assert rec.expiry_round.native >= Global.round, "Listing has expired — purchase window closed"

        # Update record
        rec.state = arc4.String(STATE_SOLD)
        rec.buyer_wallet = buyer
        rec.sold_at_round = arc4.UInt64(Global.round)
        self.listings[listing_id] = rec.copy()

        # Update counters
        self.total_active_listings.value = arc4.UInt64(self.total_active_listings.value.native - 1)
        self.total_sold_listings.value = arc4.UInt64(self.total_sold_listings.value.native + 1)

        arc4.emit("ListingSold", listing_id, buyer, rec.sold_at_round)

        # Notify Reputation contract if configured (best-effort)
        if self.reputation_app_id.value.native != 0:
            arc4.abi_call(
                "record_purchase(address,address,uint64)void",
                rec.seller_wallet,
                buyer,
                listing_id,
                app_id=self.reputation_app_id.value.native,
            )

    @arc4.abimethod(readonly=True)
    def is_sold_to_subscriber(self, listing_id: UInt64, buyer: arc4.Address) -> arc4.Bool:
        sl_exists = self.subscriber_purchases.maybe(listing_id)[1]
        if not sl_exists:
            return arc4.Bool(False)
        sl = self.subscriber_purchases[listing_id].copy()
        count = self.listings[listing_id].copy().subscription_purchase_count.as_uint64()
        for i in urange(count):
            if sl[i] == buyer:
                return arc4.Bool(True)
        return arc4.Bool(False)

    @arc4.abimethod()
    def check_and_expire(self, listing_id: UInt64) -> None:
        # Anyone may call this; expiry is a public operation
        exists = self.listings.maybe(listing_id)[1]
        if not exists:
            assert False, "Listing not found"

        rec = self.listings[listing_id].copy()
        # If not active, no-op (silent) per spec
        if rec.state.native != STATE_ACTIVE:
            return
        if rec.expiry_round.native >= Global.round:
            return
        rec.state = arc4.String(STATE_EXPIRED)
        rec.expired_at_round = arc4.UInt64(Global.round)
        self.listings[listing_id] = rec.copy()

        # Update counters
        self.total_active_listings.value = arc4.UInt64(self.total_active_listings.value.native - 1)
        self.total_expired_listings.value = arc4.UInt64(self.total_expired_listings.value.native + 1)

        arc4.emit("ListingExpired", listing_id, rec.expired_at_round)
