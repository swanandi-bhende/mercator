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

from algopy import ARC4Contract, BoxMap, UInt64, arc4, itxn


class Listing(arc4.Struct):
    """On-chain metadata for one listed trading insight.
    
    Attributes:
        price: Settlement amount in micro-USDC (1 USDC = 1_000_000 micro-USDC).
        seller: Algorand wallet address of insight author/owner.
        ipfs_hash: IPFS CID (Qm...) where full insight text is stored.
        asa_id: Associated ASA token ID (minted per listing for proof of ownership).
    """
    price: arc4.UInt64
    seller: arc4.Address
    ipfs_hash: arc4.String
    asa_id: arc4.UInt64


class InsightListing(ARC4Contract):
    """On-chain listing registry for trading insights.
    
    State:
        next_listing_id: Global counter allocating unique listing IDs (UInt64).
        listings: BoxMap(listing_id => Listing), storing all current listings.
    
    Purpose: Seller-facing contract for publishing insights + buyer-facing registry for discovery.
    """
    def __init__(self) -> None:
        self.next_listing_id = UInt64(0)
        self.listings = BoxMap(arc4.UInt64, Listing, key_prefix=b"listing")

    @arc4.abimethod()
    def create_listing(
        self,
        price: arc4.UInt64,
        seller: arc4.Address,
        ipfs_hash: arc4.String,
    ) -> arc4.UInt64:
        """Publish a new trading insight and receive seller ASA for proof-of-ownership.
        
        Purpose: Allocate unique listing ID and link IPFS content permanently on-chain.
        
        Actions:
        1. Increment next_listing_id counter \u2192 allocate new listing ID.
        2. Call itxn.AssetConfig to mint one ASA with:
           - INSIGHT token name, Mercator Insight asset name, IpfsHash as URL.
           - Seller as manager + reserve + freeze + clawback (seller controls proof token).
           - Fee=1000 micro-Algo.
        3. Store Listing struct in boxes: {price, seller, ipfs_hash, asa_id}.
        4. Increment counter for next invocation.
        5. Return listing_id to caller (frontend caches this).
        
        Args:
            price: Settlement amount (micro-USDC). e.g., 5_000_000 = 5 USDC.
            seller: Seller's Algorand wallet (58-char checksummed address).
            ipfs_hash: Content CID (e.g., \"Qm...\") pinned on Pinata.
        
        Returns:
            listing_id: Unique identifier (used in /discover results, x402 payment, escrow).
        """
        listing_id = self.next_listing_id

        # Mint one ASA for this listing and store its id with listing metadata.
        asset_result = itxn.AssetConfig(
            total=UInt64(1),
            decimals=UInt64(0),
            default_frozen=False,
            unit_name="INSIGHT",
            asset_name="Mercator Insight",
            url=ipfs_hash.native,
            manager=seller.native,
            reserve=seller.native,
            freeze=seller.native,
            clawback=seller.native,
            fee=UInt64(1000),
        ).submit()
        asa_id = asset_result.created_asset.id

        self.listings[arc4.UInt64(listing_id)] = Listing(
            price=price,
            seller=seller,
            ipfs_hash=ipfs_hash,
            asa_id=arc4.UInt64(asa_id),
        )
        self.next_listing_id = listing_id + UInt64(1)
        return arc4.UInt64(listing_id)
