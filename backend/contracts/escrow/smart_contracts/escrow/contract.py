"""Escrow contract: Proof-of-payment unlock for x402 micropayment reconciliation.

Purpose: Records confirmed buyer access after x402 payment settlement on-chain.
Acts as a gate + audit log: buyer can only fetch content after releasing this contract state.

Key Responsibilities:
1. release_after_payment(buyer, listing_id): Record unlock after x402 payment confirmed.
2. unlocked_listings: BoxMap (listing_id => UnlockRecord) tracking buyer-listing pairs.

Contract Flow in Micropayment Cycle:
1. Buyer pays USDC via x402 atomic group (confirmed on-chain).
2. post_payment_flow waits for tx confirmation, then calls release_after_payment.
3. Escrow stores UnlockRecord: {buyer, unlocked=True} associated with listing.
4. IPFS content delivery can then proceed (buyer holds proof token from ASA mint).
5. Later, seller can verify unlock records for audit/reputation updates.

Design Notes:
- release_after_payment is permissionless on caller but validates tx.sender == buyer.native.
- Seller never calls this contract directly (buyer initiates after payment confirmed).
- If payment x402 fails atomically, buyer cannot call release_after_payment (no recorded tx).
"""

from algopy import ARC4Contract, BoxMap, arc4, op


class UnlockRecord(arc4.Struct):
    """Post-payment unlock proof for one buyer-listing pair.
    
    Attributes:
        buyer: Algorand wallet address of the buyer who paid.
        unlocked: Boolean flag (always True when record created; allows future extensions).
    """
    buyer: arc4.Address
    unlocked: arc4.Bool


class Escrow(ARC4Contract):
    """Escrow settlement tracking for x402 micropayments.
    
    State:
        unlocked_listings: BoxMap(listing_id => UnlockRecord) recording buyer access grants.
    
    Purpose: Immutable on-chain proof that buyer paid for and accessed specific listing.
    """
    def __init__(self) -> None:
        self.unlocked_listings = BoxMap(arc4.UInt64, UnlockRecord, key_prefix=b"unlock")

    @arc4.abimethod()
    def release_after_payment(
        self,
        buyer: arc4.Address,
        listing_id: arc4.UInt64,
    ) -> arc4.Bool:
        """Record buyer access after x402 payment confirmed on-chain.
        
        Purpose: Post-payment gate. Called by post_payment_flow after x402 tx confirmed + indexed.
        Atomically validates that **transaction sender is the buyer** (prevents spoofing).
        
        Actions:
        1. Assert op.Txn.sender == buyer.native (confirms caller is buyer's wallet).
        2. Store UnlockRecord in boxes: {buyer, unlocked=True}.
        3. Return True to signal success.
        
        Args:
            buyer: Algorand wallet address of the buyer (must match tx sender).
            listing_id: InsightListing ID that buyer paid for.
        
        Returns:
            True if unlock recorded successfully.
        
        Raises (implicit):
            AssertionError if op.Txn.sender != buyer.native (prevents non-buyer unlock).
        
        Notes:
        - Buyer calls this **after** x402 payment confirmed and indexed.
        - No seller approval needed (payment proof is immutable on-chain).
        - UnlockRecord is append-only (supports multiple buys of same listing).
        """
        # Post-payment release path: buyer directly calls escrow after payment confirmation.
        assert op.Txn.sender == buyer.native

        self.unlocked_listings[listing_id] = UnlockRecord(
            buyer=buyer,
            unlocked=arc4.Bool(True),
        )
        return arc4.Bool(True)
