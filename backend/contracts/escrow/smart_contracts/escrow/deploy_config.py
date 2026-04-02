import os
from pathlib import Path

from algokit_utils import AlgorandClient, OnSchemaBreak, OnUpdate
from dotenv import load_dotenv
from algosdk import mnemonic, transaction
from algosdk.logic import get_application_address

from smart_contracts.artifacts.escrow.escrow_client import EscrowFactory


def _normalize_network_env() -> None:
    """Populate AlgoKit env vars from the repo's current env files."""
    repo_root = Path(__file__).resolve().parents[5]
    load_dotenv(repo_root / ".env", override=False)
    load_dotenv(repo_root / ".env.testnet", override=False)

    if not os.getenv("ALGOD_SERVER") and os.getenv("ALGOD_URL"):
        os.environ["ALGOD_SERVER"] = os.getenv("ALGOD_URL", "")
    if not os.getenv("INDEXER_SERVER") and os.getenv("INDEXER_URL"):
        os.environ["INDEXER_SERVER"] = os.getenv("INDEXER_URL", "")
    if not os.getenv("ALGOD_PORT"):
        os.environ["ALGOD_PORT"] = "443"


def deploy() -> None:
    """Deploy Escrow to the configured target network."""
    _normalize_network_env()

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
        on_update=OnUpdate.AppendApp,
    )

    app_address = result.app.app_address or get_application_address(result.app.app_id)
    app_info = algorand.client.algod.account_info(app_address)
    balance = int(app_info.get("amount", 0))
    min_balance = int(app_info.get("min-balance", 0))
    target_balance = max(min_balance + 300_000, 500_000)
    if balance < target_balance:
        top_up_amount = target_balance - balance
        private_key = mnemonic.to_private_key(deployer_mnemonic)
        params = algorand.client.algod.suggested_params()
        pay_txn = transaction.PaymentTxn(
            sender=deployer.address,
            sp=params,
            receiver=app_address,
            amt=top_up_amount,
        )
        tx_id = algorand.client.algod.send_transaction(pay_txn.sign(private_key))
        transaction.wait_for_confirmation(algorand.client.algod, tx_id, 4)

    print(f"ESCROW_APP_ID={result.app.app_id}")
    print(f"ESCROW_APP_ADDRESS={result.app.app_address}")
