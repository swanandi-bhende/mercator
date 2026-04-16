#!/usr/bin/env python3
"""Force redeploy InsightListing with a new app to enable box support."""

import sys
import os
from pathlib import Path
from dotenv import load_dotenv
from algosdk import mnemonic, transaction
from algosdk.logic import get_application_address

from algokit_utils import AlgorandClient, OnSchemaBreak, OnUpdate

# Load .env.testnet
load_dotenv(Path(".env.testnet"), override=True)

sys.path.insert(0, 'backend/contracts/insight_listing')
from smart_contracts.artifacts.insight_listing.insight_listing_client import InsightListingFactory

def deploy():
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

    # Use a new app name to force fresh deployment
    app_name = "InsightListing_BoxSupport_v2"
    
    factory = InsightListingFactory(
        algorand=algorand,
        app_name=app_name,
        default_sender=deployer.address,
    )
    
    print(f"Deploying {app_name}...")
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
        print(f"Funded app with {top_up_amount} micro-Algo")

    print(f"INSIGHT_LISTING_APP_ID={result.app.app_id}")
    print(f"INSIGHT_LISTING_APP_ADDRESS={result.app.app_address}")

if __name__ == "__main__":
    os.chdir("backend/contracts/insight_listing")
    deploy()
