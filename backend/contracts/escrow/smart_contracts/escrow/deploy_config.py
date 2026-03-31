import os

from algokit_utils import AlgorandClient, OnSchemaBreak, OnUpdate

from smart_contracts.artifacts.escrow.escrow_client import EscrowFactory


def deploy() -> None:
    """Deploy Escrow to the configured target network."""
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

    factory = EscrowFactory(
        algorand=algorand,
        app_name="Escrow",
        default_sender=deployer.address,
    )
    _, result = factory.deploy(
        on_schema_break=OnSchemaBreak.AppendApp,
        on_update=OnUpdate.UpdateApp,
    )
    print(f"ESCROW_APP_ID={result.app.app_id}")
    print(f"ESCROW_APP_ADDRESS={result.app.app_address}")
