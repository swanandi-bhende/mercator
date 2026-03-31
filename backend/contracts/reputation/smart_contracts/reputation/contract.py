from algopy import ARC4Contract, BoxMap, arc4


class Reputation(ARC4Contract):
    def __init__(self) -> None:
        self.seller_scores = BoxMap(arc4.Address, arc4.UInt64, key_prefix=b"rep")

    @arc4.abimethod()
    def update_score(self, seller: arc4.Address, new_score: arc4.UInt64) -> None:
        self.seller_scores[seller] = new_score

    @arc4.abimethod(readonly=True)
    def get_score(self, seller: arc4.Address) -> arc4.UInt64:
        return self.seller_scores.get(seller, default=arc4.UInt64(0))
