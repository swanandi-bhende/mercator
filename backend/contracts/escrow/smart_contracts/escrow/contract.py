from algopy import ARC4Contract, BoxMap, arc4, op


class UnlockRecord(arc4.Struct):
    buyer: arc4.Address
    unlocked: arc4.Bool


class Escrow(ARC4Contract):
    def __init__(self) -> None:
        self.unlocked_listings = BoxMap(arc4.UInt64, UnlockRecord, key_prefix=b"unlock")

    @arc4.abimethod()
    def release_after_payment(
        self,
        buyer: arc4.Address,
        listing_id: arc4.UInt64,
    ) -> arc4.Bool:
        # Post-payment release path: buyer directly calls escrow after payment confirmation.
        assert op.Txn.sender == buyer.native

        self.unlocked_listings[listing_id] = UnlockRecord(
            buyer=buyer,
            unlocked=arc4.Bool(True),
        )
        return arc4.Bool(True)
