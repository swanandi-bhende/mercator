from algopy import ARC4Contract, BoxMap, UInt64, arc4


class Listing(arc4.Struct):
    price: arc4.UInt64
    seller: arc4.Address
    ipfs_hash: arc4.String


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
        self.listings[arc4.UInt64(listing_id)] = Listing(
            price=price,
            seller=seller,
            ipfs_hash=ipfs_hash,
        )
        self.next_listing_id = listing_id + UInt64(1)
        return arc4.UInt64(listing_id)
