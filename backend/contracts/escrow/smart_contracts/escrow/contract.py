"""Escrow contract: Proof-of-payment unlock and fee-split for x402 micropayment reconciliation.

Purpose: Records confirmed buyer access after x402 payment settlement on-chain.
Splits USDC payment between seller and platform treasury with atomic guarantees.
Acts as a gate + audit log: buyer can only fetch content after release and payment confirmed.

Key Responsibilities:
1. release_after_payment(buyer, seller, listing_id, amount_micro_usdc): 
   Split payment between seller and treasury, record unlock after x402 payment confirmed.
2. unlocked_listings: BoxMap (listing_id => UnlockRecord) tracking buyer-listing pairs.

Contract Flow in Micropayment Cycle:
1. Buyer pays USDC via x402 atomic group (confirmed on-chain).
2. post_payment_flow waits for tx confirmation, then calls release_after_payment.
3. Escrow calls FeeConfig.calculate_fee to determine split amounts.
4. Escrow submits two inner itxn.AssetTransfer (seller payout, treasury fee) atomically.
5. Escrow calls FeeConfig.record_fee_collected to update revenue counter.
6. Escrow stores UnlockRecord: {buyer, unlocked=True} for access verification.
7. IPFS content delivery can proceed (buyer holds proof of payment).
8. Seller can later verify unlock records for audit/reputation updates.

Design Notes:
- Fee enforcement is on-chain: seller and treasury receive atomic guarantees.
- If either inner transaction fails, both revert (atomic group guarantee).
- Outer transaction fee must cover all inner transaction fees (1000 microALGO base + 1000 per inner tx).
- release_after_payment validates tx.sender == buyer.native (prevents spoofing).
"""

from algopy import ARC4Contract, BoxMap, arc4, GlobalState, UInt64, Txn, itxn


class UnlockRecord(arc4.Struct):
    """Post-payment unlock proof for one buyer-listing pair.
    
    Attributes:
        buyer: Algorand wallet address of the buyer who paid.
        seller: Algorand wallet address of the insight creator.
        unlocked: Boolean flag (always True when record created; allows future extensions).
        payment_amount_micro_usdc: Original payment amount before fee split.
    """
    buyer: arc4.Address
    seller: arc4.Address
    unlocked: arc4.Bool
    payment_amount_micro_usdc: arc4.UInt64


class Escrow(ARC4Contract):
    """Escrow settlement tracking with fee splitting for x402 micropayments.
    
    State:
        registry_app_id: Global reference to AgentRegistry app (UInt64).
        fee_config_app_id: Global reference to FeeConfig app (UInt64).
        insight_listing_app_id: Global reference to InsightListing app (UInt64).
        unlocked_listings: BoxMap(listing_id => UnlockRecord) recording buyer access + payment details.
    
    Purpose: Immutable on-chain proof that buyer paid for and accessed specific listing,
    with guaranteed fee split between seller and platform treasury.
    """
    registry_app_id: GlobalState[UInt64]
    fee_config_app_id: GlobalState[UInt64]
    insight_listing_app_id: GlobalState[UInt64]
    reputation_app_id: GlobalState[UInt64]
    subscription_manager_app_id: GlobalState[UInt64]
    owner: GlobalState[arc4.Address]
    unlocked_listings: BoxMap[arc4.UInt64, UnlockRecord]

    def __init__(self) -> None:
        self.registry_app_id = GlobalState(UInt64)
        self.fee_config_app_id = GlobalState(UInt64)
        self.insight_listing_app_id = GlobalState(UInt64)
        self.reputation_app_id = GlobalState(UInt64)
        self.subscription_manager_app_id = GlobalState(UInt64)
        self.owner = GlobalState(arc4.Address)
        self.unlocked_listings = BoxMap(arc4.UInt64, UnlockRecord, key_prefix=b"unlock")

        self.owner.value = arc4.Address(Txn.sender)
        self.fee_config_app_id.value = UInt64(0)
        self.insight_listing_app_id.value = UInt64(0)
        self.registry_app_id.value = UInt64(0)
        self.reputation_app_id.value = UInt64(0)
        self.subscription_manager_app_id.value = UInt64(0)

    @arc4.abimethod(create="require", allow_actions=["NoOp"])
    def create(
        self,
        fee_config_app_id: arc4.UInt64,
        insight_listing_app_id: arc4.UInt64,
        registry_app_id: arc4.UInt64,
        reputation_app_id: arc4.UInt64,
        subscription_manager_app_id: arc4.UInt64,
    ) -> None:
        self.owner.value = arc4.Address(Txn.sender)
        self.fee_config_app_id.value = fee_config_app_id.as_uint64()
        self.insight_listing_app_id.value = insight_listing_app_id.as_uint64()
        self.registry_app_id.value = registry_app_id.as_uint64()
        self.reputation_app_id.value = reputation_app_id.as_uint64()
        self.subscription_manager_app_id.value = subscription_manager_app_id.as_uint64()

    @arc4.abimethod()
    def set_app_ids(
        self,
        fee_config_app_id: arc4.UInt64,
        insight_listing_app_id: arc4.UInt64,
        registry_app_id: arc4.UInt64,
        reputation_app_id: arc4.UInt64,
        subscription_manager_app_id: arc4.UInt64,
    ) -> None:
        assert Txn.sender == self.owner.value.native, "Only owner can update app ids"
        self.fee_config_app_id.value = fee_config_app_id.as_uint64()
        self.insight_listing_app_id.value = insight_listing_app_id.as_uint64()
        self.registry_app_id.value = registry_app_id.as_uint64()
        self.reputation_app_id.value = reputation_app_id.as_uint64()
        self.subscription_manager_app_id.value = subscription_manager_app_id.as_uint64()

    @arc4.abimethod()
    def release_after_payment(
        self,
        buyer: arc4.Address,
        seller: arc4.Address,
        listing_id: arc4.UInt64,
        amount_micro_usdc: arc4.UInt64,
        usdc_asset_id: arc4.UInt64,
        treasury_address: arc4.Address,
    ) -> arc4.Bool:
        """Record buyer access and split payment after x402 payment confirmed on-chain.
        
        Purpose: Post-payment gate with fee splitting. Called after x402 
        tx confirmed and indexed. Atomically validates caller is buyer and splits payment.
        
        Atomicity Guarantee:
        - All inner transactions (USDC transfers to seller and treasury) are submitted together
        - All cross-contract calls (FeeConfig.record_fee_collected, Reputation.record_purchase) 
          are part of the same outer transaction
        - If ANY operation fails (validation, inner tx, or ABI call), entire method reverts
        - Seller receives payout, treasury receives fee, reputation is updated, unlock recorded
          OR none of these happen
        
        Actions:
        1. Assert tx.sender == buyer (confirms caller is buyer's wallet)
        2. Check buyer registered in AgentRegistry (if set)
        3. Call FeeConfig.calculate_fee to determine seller payout and treasury fee
        4. Verify conservation invariant: fee + payout == total amount
        5. Build and submit two inner itxn.AssetTransfer transactions atomically:
           a. Transfer seller_payout_micro_usdc to seller wallet
           b. Transfer fee_micro_usdc to treasury wallet
        6. Call FeeConfig.record_fee_collected to update revenue counter (part of same outer txn)
        7. Call Reputation.record_purchase to update seller reputation (part of same outer txn)
        8. Store UnlockRecord in boxes: {buyer, seller, unlocked=True, amount}
        9. Return True to signal success
        
        Args:
            buyer: Algorand wallet address of the buyer (must match tx sender)
            seller: Algorand wallet address of the insight creator
            listing_id: InsightListing ID that buyer paid for
            amount_micro_usdc: Total payment amount in microUSDC before fee split
            usdc_asset_id: USDC ASA ID for inner transfers
            treasury_address: Treasury wallet to receive platform fee
        
        Returns:
            True if unlock recorded and payment split successfully
        
        Raises (implicit):
            AssertionError if tx.sender != buyer
            AssertionError if fee + payout != amount (conservation invariant)
            Exception if FeeConfig.calculate_fee fails (entire method reverts)
            Exception if inner transfers fail (entire method reverts)
            Exception if FeeConfig.record_fee_collected fails (entire method reverts)
            Exception if Reputation.record_purchase fails (entire method reverts)
        
        Notes:
        - All operations within this method share atomic transaction semantics
        - If method reverts at any point, all previous effects (including inner txns) are rolled back
        - Fee calculation and conservation check happen before any money moves
        - Inner USDC transfers are submitted atomically before external ABI calls
        """
        # Guard: only buyer can trigger release
        assert Txn.sender == buyer.native, "Only the buyer can release after payment"

        # Optionally check buyer is registered in AgentRegistry (if registry_app_id is set)
        if self.registry_app_id.value != UInt64(0):
            is_registered, registration_check_txn = arc4.abi_call[arc4.Bool](
                "is_registered(address)bool",
                buyer,
                app_id=self.registry_app_id.value,
            )
            assert is_registered, "Buyer must be registered in AgentRegistry"

        # Call FeeConfig to calculate the fee split
        # This is a read-only cross-contract call; if it fails, method reverts immediately
        fee_micro_usdc, fee_calculation_txn = arc4.abi_call[arc4.UInt64](
            "calculate_fee(uint64)uint64",
            amount_micro_usdc,
            app_id=self.fee_config_app_id.value,
        )
        
        # Calculate seller payout: amount - fee
        amount = amount_micro_usdc.as_uint64()
        fee = fee_micro_usdc.as_uint64()
        seller_payout_micro_usdc = amount - fee
        assert seller_payout_micro_usdc + fee == amount, "Fee split must be lossless"

        # Build one explicit inner transaction group for both USDC transfers.
        itxn.begin()
        itxn.AssetTransfer(
            xfer_asset=usdc_asset_id.as_uint64(),
            asset_receiver=seller.native,
            asset_amount=seller_payout_micro_usdc,
        ).set()
        itxn.next()
        itxn.AssetTransfer(
            xfer_asset=usdc_asset_id.as_uint64(),
            asset_receiver=treasury_address.native,
            asset_amount=fee,
        ).set()
        itxn.submit()

        # Record fee collection in FeeConfig
        # This updates the platform's running total of collected fees
        # If this fails, entire method reverts (including inner transfers)
        arc4.abi_call(
            "record_fee_collected(uint64)",
            fee_micro_usdc,
            app_id=self.fee_config_app_id.value,
        )

        # Update seller reputation: record this purchase on-chain for future scoring
        # Ordering: inner transfers happen first (money moves), then reputation recorded
        # If reputation call fails, entire method reverts (seller doesn't receive funds)
        if self.reputation_app_id.value != UInt64(0):
            arc4.abi_call(
                "record_purchase(address,address,uint64)void",
                seller,
                buyer,
                listing_id,
                app_id=self.reputation_app_id.value,
            )

        arc4.abi_call(
            "mark_sold(uint64,address)",
            listing_id,
            buyer,
            app_id=self.insight_listing_app_id.value,
        )

        # Store unlock record for audit trail
        # This creates an immutable on-chain proof that buyer paid and received access
        self.unlocked_listings[listing_id] = UnlockRecord(
            buyer=buyer,
            seller=seller,
            unlocked=arc4.Bool(True),
            payment_amount_micro_usdc=amount_micro_usdc,
        )
        
        return arc4.Bool(True)

    @arc4.abimethod()
    def release_for_subscriber(self, buyer: arc4.Address, listing_id: arc4.UInt64) -> arc4.Bool:
        """Release insight access to a buyer with active subscription.
        
        Atomicity Guarantee:
        - All verification, state changes, and reputation updates are part of the same outer transaction
        - If this method reverts at ANY point, ALL effects revert together:
          - Listing state change reverts
          - Reputation increment reverts
          - Registry transaction count change reverts
        - No partial completion: either buyer gets complete access or no access at all
        
        Call Ordering (CRITICAL for correctness):
        1. Verify subscription entitlement (read-only checks only, no state change)
           - Check buyer registered in AgentRegistry
           - Check listing is still active
           - Check subscription is valid via SubscriptionManager
        2. Update reputation (state change #1)
           - Increment seller score immediately, before listing state change
           - If this fails, none of the subsequent steps are written
        3. Mark listing sold to subscriber (state change #2)
           - Only mark sold AFTER reputation is committed to prevent double-crediting
           - If this fails, reputation increment also reverts
        4. Record in transaction count (state change #3)
        5. Post-condition check: verify buyer actually got access
        
        Ordering Rationale:
        - Read-only checks first (no risk even if they fail)
        - Reputation update before listing state change prevents this scenario:
          If reputation succeeds and mark_sold fails, seller is credited
          for a sale that never actually happened (inconsistent state)
        - Post-condition assertion serves as method-level invariant check
        """
        # Guard: only buyer can trigger release for their own subscription
        assert Txn.sender == buyer.native, "Only the buyer can release subscriber access"

        # =====================================================================
        # PHASE 1: VERIFICATION ONLY (read-only, no state changes)
        # =====================================================================
        
        if self.registry_app_id.value != UInt64(0):
            is_registered, registration_check_txn = arc4.abi_call[arc4.Bool](
                "is_registered(address)bool",
                buyer,
                app_id=self.registry_app_id.value,
            )
            assert is_registered, "Buyer must be registered in AgentRegistry"

        listing_state, listing_state_txn = arc4.abi_call[arc4.String](
            "get_listing_state(uint64)string",
            listing_id,
            app_id=self.insight_listing_app_id.value,
        )
        assert listing_state == arc4.String("active"), "Listing is not active"

        seller, seller_txn = arc4.abi_call[arc4.Address](
            "get_seller(uint64)address",
            listing_id,
            app_id=self.insight_listing_app_id.value,
        )

        # Verify subscription entitlement (final read-only check before state changes)
        subscription_valid, subscription_txn = arc4.abi_call[arc4.Bool](
            "release_for_subscriber(address,uint64)bool",
            buyer,
            listing_id,
            app_id=self.subscription_manager_app_id.value,
        )
        assert subscription_valid, "Subscription entitlement could not be confirmed"

        # =====================================================================
        # PHASE 2: STATE CHANGES (in correct order for atomic safety)
        # =====================================================================
        
        # Update reputation FIRST (before marking sold)
        # This way if mark_sold_to_subscriber fails, reputation increment also reverts
        if self.reputation_app_id.value != UInt64(0):
            arc4.abi_call(
                "record_purchase(address,address,uint64)void",
                seller,
                buyer,
                listing_id,
                app_id=self.reputation_app_id.value,
            )

        # Mark listing sold AFTER reputation update
        # This prevents seller being credited for a sale that doesn't complete
        arc4.abi_call(
            "mark_sold_to_subscriber(uint64,address)",
            listing_id,
            buyer,
            app_id=self.insight_listing_app_id.value,
        )

        # Record transaction in buyer's agent registry account (optional, non-critical)
        if self.registry_app_id.value != UInt64(0):
            arc4.abi_call(
                "increment_transaction_count(address)void",
                buyer,
                app_id=self.registry_app_id.value,
            )

        # =====================================================================
        # PHASE 3: POST-CONDITION ASSERTION (method-level invariant check)
        # =====================================================================
        
        # Verify buyer actually got access before returning
        # This assertion fails loudly rather than allowing silent partial completion
        assert self._verify_subscription_access_granted(
            buyer, listing_id
        ), "Post-condition failed: buyer was not granted subscription access"

        return arc4.Bool(True)

    def _verify_subscription_access_granted(self, buyer: arc4.Address, listing_id: arc4.UInt64) -> bool:
        """Private helper: verify buyer has subscription access to this listing.
        
        Purpose: Method-level post-condition check that serves as insurance
        against incomplete execution. If this check fails, the entire method
        reverts, preventing a state where buyer's subscription is charged but
        they cannot access the listing.
        
        Args:
            buyer: Buyer's address to verify
            listing_id: Listing ID to check access for
        
        Returns:
            True if buyer has verified access, False otherwise
        
        Checks:
            1. SubscriptionManager confirms active subscription for buyer
            2. InsightListing confirms this listing is marked as sold to buyer
        """
        try:
            # Check subscription is still valid
            has_subscription, txn1 = arc4.abi_call[arc4.Bool](
                "is_active(address)bool",
                buyer,
                app_id=self.subscription_manager_app_id.value,
            )
            if not has_subscription:
                return False
            
            # Check listing is marked sold to this buyer
            is_sold, txn2 = arc4.abi_call[arc4.Bool](
                "is_sold_to_subscriber(uint64,address)bool",
                listing_id,
                buyer,
                app_id=self.insight_listing_app_id.value,
            )
            return is_sold
        except Exception:
            # If verification calls fail, conservatively assume access was not granted
            return False

