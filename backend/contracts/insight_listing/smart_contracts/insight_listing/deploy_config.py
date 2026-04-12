"""Deploy configuration for InsightListing contract.

Purpose: Deploy listing registry contract used by sellers to publish CID+price metadata.
"""

import os

from algokit_utils import AlgorandClient, OnSchemaBreak, OnUpdate

from smart_contracts.artifacts.insight_listing.insight_listing_client import (
    InsightListingFactory,
)


def deploy() -> None:
    """Deploy InsightListing to the configured target network."""
    # Deploys/updates listing registry app used by /list and /discover backend flows.
    deployer_mnemonic = os.getenv("DEPLOYER_MNEMONIC")
    deployer_address = os.getenv("DEPLOYER_ADDRESS")
    if not deployer_mnemonic:
        raise ValueError("Missing DEPLOYER_MNEMONIC")

    algorand = AlgorandClient.from_environment()
    deployer = algorand.account.from_mnemonic(
        mnemonic=deployer_mnemonic,
        sender=deployer_address or None,
    )
    algorand.set_default_signer(deployer)

    factory = InsightListingFactory(
        algorand=algorand,
        app_name="InsightListing",
        default_sender=deployer.address,
    )
    _, result = factory.deploy(
        on_schema_break=OnSchemaBreak.AppendApp,
        on_update=OnUpdate.AppendApp,
    )
    print(f"INSIGHT_LISTING_APP_ID={result.app.app_id}")
    print(f"INSIGHT_LISTING_APP_ADDRESS={result.app.app_address}")
