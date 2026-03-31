from algopy import ARC4Contract, BoxMap, UInt64, arc4, itxn


class Listing(arc4.Struct):
    price: arc4.UInt64
    seller: arc4.Address
    ipfs_hash: arc4.String
    asa_id: arc4.UInt64


class InsightListing(ARC4Contract):
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
