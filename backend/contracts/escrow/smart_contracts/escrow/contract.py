from algopy import ARC4Contract, BoxMap, UInt64, arc4, gtxn, op


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
        group_index = op.Txn.group_index

        # Require a preceding payment transaction in the same atomic group.
        assert group_index > UInt64(0)
        payment_txn = gtxn.PaymentTransaction(group_index - UInt64(1))

        # x402-style payment guard: buyer pays this app address with non-zero amount.
        assert payment_txn.sender == buyer.native
        assert payment_txn.receiver == op.Global.current_application_address
        assert payment_txn.amount > UInt64(0)

        self.unlocked_listings[listing_id] = UnlockRecord(
            buyer=buyer,
            unlocked=arc4.Bool(True),
        )
        return arc4.Bool(True)
