import os
import json
import asyncio

from algokit_utils import AlgorandClient
from contracts.reputation import ReputationClient
from backend.utils.runtime_env import normalize_network_env
from backend.utils.ipfs import upload_insight_to_ipfs, store_cid_in_listing
from backend.tools.x402_payment import trigger_x402_payment


async def main() -> None:
    normalize_network_env()
    seller = os.getenv("DEPLOYER_ADDRESS", "").strip()
    buyer = os.getenv("BUYER_WALLET", "").strip() or os.getenv("BUYER_ADDRESS", "").strip()
    listing_app_id = int(os.getenv("INSIGHT_LISTING_APP_ID", "0"))
    rep_app_id = int(os.getenv("REPUTATION_APP_ID", "0"))
    if not seller or not buyer or listing_app_id <= 0 or rep_app_id <= 0:
        raise RuntimeError("Missing required env for final purchase check")

    algorand = AlgorandClient.from_environment()
    dep_mn = os.getenv("DEPLOYER_MNEMONIC", "").strip()
    if dep_mn:
        signer = algorand.account.from_mnemonic(mnemonic=dep_mn, sender=seller)
        algorand.set_default_signer(signer)

    rep_client = ReputationClient(algorand=algorand, app_id=rep_app_id, default_sender=seller or None)
    before_raw = rep_client.state.box.seller_scores.get_value(seller)
    before = int(before_raw) if before_raw is not None else 0

    reuse_listing_id = int(os.getenv("REUSE_LISTING_ID", "0"))
    if reuse_listing_id > 0:
        listing_id = reuse_listing_id
        asa_id = -1
        cid = "reused-existing-listing"
    else:
        cid = await upload_insight_to_ipfs(
            "Final security audit purchase run insight: NIFTY micro breakout with strict risk stops.",
            filename="security-final-run.txt",
        )
        listing_id, asa_id = store_cid_in_listing(
            cid=cid,
            listing_app_id=listing_app_id,
            seller_address=seller,
            price=1_000_000,
        )

    payment_raw = await trigger_x402_payment.ainvoke(
        {
            "listing_id": listing_id,
            "buyer_address": buyer,
            "amount_usdc": 1.0,
            "user_approval_input": "approve",
        }
    )
    payment = json.loads(payment_raw)

    after_raw = rep_client.state.box.seller_scores.get_value(seller)
    after = int(after_raw) if after_raw is not None else 0

    print(
        json.dumps(
            {
                "seller": seller,
                "buyer": buyer,
                "reputation_before": before,
                "reputation_after": after,
                "reputation_delta": after - before,
                "listing_id": listing_id,
                "asa_id": asa_id,
                "cid": cid,
                "payment_response": payment,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
