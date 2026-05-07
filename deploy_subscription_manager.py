#!/usr/bin/env python3
"""Deploy the SubscriptionManager contract to the configured target network."""

from __future__ import annotations

import os
from pathlib import Path

from algokit_utils import AlgorandClient, AppClientMethodCallCreateParams, AppClientMethodCallParams, AppFactory, AppFactoryParams, Arc56Contract, OnSchemaBreak, OnUpdate
from algosdk import mnemonic, transaction
from algosdk.logic import get_application_address
from dotenv import load_dotenv


def _normalize_network_env() -> None:
    repo_root = Path(__file__).resolve().parent
    load_dotenv(repo_root / ".env", override=False)
    load_dotenv(repo_root / ".env.testnet", override=True)

    if not os.getenv("ALGOD_SERVER") and os.getenv("ALGOD_URL"):
        os.environ["ALGOD_SERVER"] = os.getenv("ALGOD_URL", "")
    if not os.getenv("INDEXER_SERVER") and os.getenv("INDEXER_URL"):
        os.environ["INDEXER_SERVER"] = os.getenv("INDEXER_URL", "")
    if not os.getenv("ALGOD_PORT"):
        os.environ["ALGOD_PORT"] = "443"


def deploy() -> int:
    _normalize_network_env()

    deployer_mnemonic = os.getenv("DEPLOYER_MNEMONIC")
    deployer_address = os.getenv("DEPLOYER_ADDRESS")
    if not deployer_mnemonic:
        raise ValueError("Missing DEPLOYER_MNEMONIC")

    repo_root = Path(__file__).resolve().parent
    app_spec_path = repo_root / "backend/contracts/backend/contracts/subscription_manager_artifacts/SubscriptionManager.arc56.json"
    app_spec = Arc56Contract.from_json(app_spec_path.read_text())

    algorand = AlgorandClient.from_environment()
    deployer = algorand.account.from_mnemonic(
        mnemonic=deployer_mnemonic,
        sender=deployer_address or None,
    )
    algorand.set_default_signer(deployer)

    factory = AppFactory(
        AppFactoryParams(
            algorand=algorand,
            app_spec=app_spec,
            app_name="SubscriptionManager",
            default_sender=deployer.address,
        )
    )

    monthly_rate_micro_usdc = int(os.getenv("SUBSCRIPTION_MONTHLY_RATE_MICRO_USDC", "50000000") or 50000000)
    rounds_per_month = int(os.getenv("SUBSCRIPTION_ROUNDS_PER_MONTH", "17280") or 17280)
    usdc_asset_id = int(os.getenv("USDC_ASSET_ID", "10458941") or 10458941)

    create_params = AppClientMethodCallCreateParams(
        sender=deployer.address,
        method="create(uint64,uint64,uint64)void",
        args=[monthly_rate_micro_usdc, rounds_per_month, usdc_asset_id],
    )

    app_client, result = factory.deploy(
        on_schema_break=OnSchemaBreak.AppendApp,
        on_update=OnUpdate.AppendApp,
        create_params=create_params,
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

    opt_in_call = AppClientMethodCallParams(
        sender=deployer.address,
        method="opt_in_usdc()void",
    )
    opt_in_result = app_client.send.call(opt_in_call)

    escrow_app_id = int(os.getenv("ESCROW_APP_ID", "0") or 0)
    if escrow_app_id:
        escrow_call = AppClientMethodCallParams(
            sender=deployer.address,
            method="set_escrow_app(uint64)void",
            args=[escrow_app_id],
        )
        app_client.send.call(escrow_call)

    print(f"SUBSCRIPTION_MANAGER_APP_ID={result.app.app_id}")
    print(f"SUBSCRIPTION_MANAGER_APP_ADDRESS={result.app.app_address}")
    print(f"OPT_IN_TXN={getattr(opt_in_result, 'tx_id', '')}")
    return int(result.app.app_id)


if __name__ == "__main__":
    deploy()