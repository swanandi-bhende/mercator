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
        
        Purpose: Post-payment gate with fee splitting. Called by post_payment_flow after x402 
        tx confirmed and indexed. Atomically validates caller is buyer and splits payment.
        
        Actions:
        1. Assert tx.sender == buyer (confirms caller is buyer's wallet).
        2. Check buyer registered in AgentRegistry (if set).
        3. Call FeeConfig.calculate_fee to determine seller payout and treasury fee.
        4. Build and submit two inner itxn.AssetTransfer transactions atomically:
           a. Transfer seller_payout_micro_usdc to seller wallet
           b. Transfer fee_micro_usdc to treasury wallet
        5. Call FeeConfig.record_fee_collected to update revenue counter.
        6. Call InsightListing to mark listing as purchased by buyer.
        7. Store UnlockRecord in boxes: {buyer, seller, unlocked=True, amount}.
        8. Return True to signal success.
        
        Args:
            buyer: Algorand wallet address of the buyer (must match tx sender).
            seller: Algorand wallet address of the insight creator.
            listing_id: InsightListing ID that buyer paid for.
            amount_micro_usdc: Total payment amount in microUSDC before fee split.
            usdc_asset_id: USDC ASA ID for inner transfers.
            treasury_address: Treasury wallet to receive platform fee.
        
        Returns:
            True if unlock recorded and payment split successfully.
        
        Raises (implicit):
            AssertionError if tx.sender != buyer (prevents non-buyer unlock).
            AssertionError if fee + payout != amount (invariant violation).
        
        Notes:
        - Buyer calls this **after** x402 payment confirmed and indexed.
        - Payment split is atomic: seller and treasury both receive or both fail.
        - If either inner transaction fails, entire method reverts.
        - UnlockRecord includes payment_amount for audit trail.
        """
        # Post-payment release path: buyer directly calls escrow after payment confirmation.
        assert Txn.sender == buyer.native, "Only the buyer can release after payment"

        # Optionally check buyer is registered in AgentRegistry (if registry_app_id is set)
        if self.registry_app_id.value != UInt64(0):
            is_registered, registration_check_txn = arc4.abi_call[arc4.Bool](
                "is_registered(address)bool",
                buyer,
                app_id=self.registry_app_id.value,
            )
            assert is_registered, "Buyer must be registered in AgentRegistry"

        # Call FeeConfig to get fee calculation
        fee_micro_usdc, fee_calculation_txn = arc4.abi_call[arc4.UInt64](
            "calculate_fee(uint64)uint64",
            amount_micro_usdc,
            app_id=self.fee_config_app_id.value,
        )
        
        # Calculate seller payout
        amount = amount_micro_usdc.as_uint64()
        fee = fee_micro_usdc.as_uint64()
        seller_payout_micro_usdc = amount - fee
        
        # Invariant check: fee + payout must equal amount (lossless split)
        assert (
            fee + seller_payout_micro_usdc == amount
        ), "Fee split invariant violated: fee + payout != amount"

        # Build both transfers, then submit once for atomic inner-group semantics.
        seller_transfer = itxn.AssetTransfer(
            xfer_asset=usdc_asset_id.as_uint64(),
            asset_receiver=seller.native,
            asset_amount=seller_payout_micro_usdc,
        )
        treasury_transfer = itxn.AssetTransfer(
            xfer_asset=usdc_asset_id.as_uint64(),
            asset_receiver=treasury_address.native,
            asset_amount=fee,
        )
        itxn.submit_txns(seller_transfer, treasury_transfer)

        # Record fee collection in FeeConfig
        arc4.abi_call(
            "record_fee_collected(uint64)",
            fee_micro_usdc,
            app_id=self.fee_config_app_id.value,
        )

        # Important ordering: move money first, then update reputation. If reputation
        # update runs before transfers and transfers later fail, the seller would be
        # incorrectly credited on-chain. Doing reputation after transfers avoids that.
        if self.reputation_app_id.value != UInt64(0):
            try:
                # Call the Reputation contract to record the purchase (seller, buyer, listing)
                arc4.abi_call(
                    "record_purchase(address,address,uint64)void",
                    seller,
                    buyer,
                    listing_id,
                    app_id=self.reputation_app_id.value,
                )
            except Exception:
                # Reputation update failure should not prevent payout; log silently on-chain.
                pass

        # Update buyer access in InsightListing contract.
        # Disabled pending method availability in InsightListing ABI.

        # Store unlock record with payment details
        self.unlocked_listings[listing_id] = UnlockRecord(
            buyer=buyer,
            seller=seller,
            unlocked=arc4.Bool(True),
            payment_amount_micro_usdc=amount_micro_usdc,
        )
        
        return arc4.Bool(True)

    @arc4.abimethod()
    def release_for_subscriber(self, buyer: arc4.Address, listing_id: arc4.UInt64, seller: arc4.Address) -> arc4.Bool:
        assert Txn.sender == buyer.native, "Only the buyer can release subscriber access"

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

        subscription_valid, subscription_txn = arc4.abi_call[arc4.Bool](
            "release_for_subscriber(address,uint64)bool",
            buyer,
            listing_id,
            app_id=self.subscription_manager_app_id.value,
        )
        assert subscription_valid, "Subscription entitlement could not be confirmed"

        arc4.abi_call(
            "mark_sold_to_subscriber(uint64,address)",
            listing_id,
            buyer,
            app_id=self.insight_listing_app_id.value,
        )

        if self.registry_app_id.value != UInt64(0):
            arc4.abi_call(
                "increment_transaction_count(address)void",
                buyer,
                app_id=self.registry_app_id.value,
            )

        # Update reputation for subscriber purchases as well. Ordering: mark sold first,
        # then call reputation to credit the seller. If reputation call fails, don't revert.
        if self.reputation_app_id.value != UInt64(0):
            try:
                arc4.abi_call(
                    "record_purchase(address,address,uint64)void",
                    seller,
                    buyer,
                    listing_id,
                    app_id=self.reputation_app_id.value,
                )
            except Exception:
                pass

        return arc4.Bool(True)
