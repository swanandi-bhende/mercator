import asyncio
import json
import os

from algosdk import account

from backend import agent as agent_module
from backend.tools.x402_payment import trigger_x402_payment
from backend.utils.ipfs import store_cid_in_listing, ListingStoreError


async def run_low_reputation_case() -> dict:
    class _FakeSemanticTool:
        async def ainvoke(self, _payload):
            return [{"listing_id": 999, "price": 1.0, "reputation": 10}]

    async def _fake_eval(state):
        updated = dict(state)
        updated["evaluation"] = "Reasoning: low reputation\nDecision: BUY"
        updated["decision"] = "BUY"
        return updated

    original_tool = agent_module.semantic_search_tool
    original_eval = agent_module.evaluate_insights
    try:
        agent_module.semantic_search_tool = _FakeSemanticTool()
        agent_module.evaluate_insights = _fake_eval
        result = await agent_module.run_agent(
            user_query="edge low reputation",
            user_approval_input="approve",
            force_buy_for_test=False,
        )
        return {
            "name": "low_reputation_seller",
            "result": result,
        }
    finally:
        agent_module.semantic_search_tool = original_tool
        agent_module.evaluate_insights = original_eval


async def run_insufficient_balance_case() -> dict:
    _, empty_wallet = account.generate_account()
    raw = await trigger_x402_payment.ainvoke(
        {
            "listing_id": 47,
            "buyer_address": empty_wallet,
            "amount_usdc": 1.0,
            "user_approval_input": "approve",
        }
    )
    return {
        "name": "insufficient_usdc_balance",
        "result": json.loads(raw),
    }


async def run_invalid_wallet_case() -> dict:
    raw = await trigger_x402_payment.ainvoke(
        {
            "listing_id": 47,
            "buyer_address": "INVALID_WALLET",
            "amount_usdc": 1.0,
            "user_approval_input": "approve",
        }
    )
    return {
        "name": "invalid_wallet_address",
        "result": json.loads(raw),
    }


def run_malformed_cid_case() -> dict:
    seller = os.getenv("DEPLOYER_ADDRESS", "").strip()
    listing_app_id = int(os.getenv("INSIGHT_LISTING_APP_ID", "0"))
    try:
        store_cid_in_listing(
            cid="INVALID_CID_123",
            listing_app_id=listing_app_id,
            seller_address=seller,
            price=1_000_000,
        )
    except ListingStoreError as exc:
        return {
            "name": "malformed_ipfs_cid",
            "result": {
                "error": "LISTING_STORE_ERROR",
                "message": str(exc),
            },
        }
    return {
        "name": "malformed_ipfs_cid",
        "result": {
            "error": "UNEXPECTED_PASS",
            "message": "Malformed CID unexpectedly succeeded",
        },
    }


async def main() -> None:
    results = []
    results.append(await run_low_reputation_case())
    results.append(await run_insufficient_balance_case())
    results.append(await run_invalid_wallet_case())
    results.append(run_malformed_cid_case())
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
