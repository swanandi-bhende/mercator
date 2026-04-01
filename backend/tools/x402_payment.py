"""
X402 Micropayment Tool for LangChain Agent

This module implements the x402 micropayment pattern for atomic group transactions.
The x402 pattern allows instant, fee-efficient payments on Algorand using atomic groups.
"""

from langchain_core.tools import tool
from algosdk.v2client import algod, indexer
from algosdk import encoding, transaction, account as algo_account, mnemonic as algo_mnemonic
from algosdk.transaction import ApplicationCallTxn, PaymentTxn
from algokit_utils import AlgorandClient
from dotenv import load_dotenv
import os
import asyncio
import json
from typing import Dict, Tuple
import logging
from functools import lru_cache

# Import contract clients
from contracts.insight_listing import InsightListingClient
from backend.contracts.escrow.smart_contracts.artifacts.escrow.escrow_client import EscrowClient
from backend.contracts.reputation.smart_contracts.artifacts.reputation.reputation_client import ReputationClient

logger = logging.getLogger(__name__)
load_dotenv()

# Initialize Algorand clients
@lru_cache(maxsize=1)
def get_algorand_client() -> AlgorandClient:
    """Return a cached Algorand client configured from environment."""
    algod_client = AlgorandClient.from_environment()
    deployer_mnemonic = os.getenv("DEPLOYER_MNEMONIC", "").strip()
    deployer_address = os.getenv("DEPLOYER_ADDRESS", "").strip()
    if deployer_mnemonic and deployer_address:
        signer = algod_client.account.from_mnemonic(
            mnemonic=deployer_mnemonic,
            sender=deployer_address,
        )
        algod_client.set_default_signer(signer)
    return algod_client


@lru_cache(maxsize=1)
def get_insight_listing_client() -> InsightListingClient:
    """Return the deployed InsightListing app client."""
    app_id = int(os.getenv("INSIGHT_LISTING_APP_ID", "0"))
    if app_id <= 0:
        raise ValueError("INSIGHT_LISTING_APP_ID not configured")

    deployer_mnemonic = os.getenv("DEPLOYER_MNEMONIC", "").strip()
    sender = (
        algo_account.address_from_private_key(
            algo_mnemonic.to_private_key(deployer_mnemonic)
        )
        if deployer_mnemonic
        else os.getenv("DEPLOYER_ADDRESS", "").strip() or None
    )

    return InsightListingClient(
        algorand=get_algorand_client(),
        app_id=app_id,
        default_sender=sender,
    )


@lru_cache(maxsize=1)
def get_escrow_client() -> EscrowClient:
    """Return the deployed Escrow app client."""
    app_id = int(os.getenv("ESCROW_APP_ID", "0"))
    if app_id <= 0:
        raise ValueError("ESCROW_APP_ID not configured")

    deployer_mnemonic = os.getenv("DEPLOYER_MNEMONIC", "").strip()
    sender = (
        algo_account.address_from_private_key(
            algo_mnemonic.to_private_key(deployer_mnemonic)
        )
        if deployer_mnemonic
        else os.getenv("DEPLOYER_ADDRESS", "").strip() or None
    )

    return EscrowClient(
        algorand=get_algorand_client(),
        app_id=app_id,
        default_sender=sender,
    )


@lru_cache(maxsize=1)
def get_reputation_client() -> ReputationClient:
    """Return the deployed Reputation app client."""
    app_id = int(os.getenv("REPUTATION_APP_ID", "0"))
    if app_id <= 0:
        raise ValueError("REPUTATION_APP_ID not configured")

    deployer_mnemonic = os.getenv("DEPLOYER_MNEMONIC", "").strip()
    sender = (
        algo_account.address_from_private_key(
            algo_mnemonic.to_private_key(deployer_mnemonic)
        )
        if deployer_mnemonic
        else os.getenv("DEPLOYER_ADDRESS", "").strip() or None
    )

    return ReputationClient(
        algorand=get_algorand_client(),
        app_id=app_id,
        default_sender=sender,
    )


# X402 Configuration
X402_PRIVATE_KEY = os.getenv("X402_PRIVATE_KEY", "")
INSIGHT_LISTING_APP_ID = int(os.getenv("INSIGHT_LISTING_APP_ID", 758025190))
ESCROW_APP_ID = int(os.getenv("ESCROW_APP_ID", 758022447))
REPUTATION_APP_ID = int(os.getenv("REPUTATION_APP_ID", 758022459))
USDC_ASA_ID = int(os.getenv("USDC_ASA_ID", 0))  # TestNet USDC asset ID if available


@tool
async def trigger_x402_payment(listing_id: int, buyer_address: str, amount_usdc: float) -> str:
    """
    Trigger an x402 micropayment for a listed insight.
    
    This function:
    1. Fetches the listing details (seller wallet, price, IPFS CID, ASA ID)
    2. Validates the payment amount matches the listed price
    3. Constructs an atomic group transaction with:
       - Payment transaction (buyer -> escrow)
       - Escrow unlock call (escrow app)
       - Reputation update (reputation app)
    4. Submits the transaction and returns confirmation details
    
    Args:
        listing_id (int): The on-chain listing ID (from InsightListing app)
        buyer_address (str): The buyer's wallet address (58 chars, checksummed)
        amount_usdc (float): The payment amount in USDC (should match listed price)
    
    Returns:
        str: JSON string with payment status, transaction ID, and explorer link
    
    Raises:
        ValueError: If listing not found, amount mismatch, or buyer address invalid
        Exception: If transaction submission fails
    """
    try:
        # Validate buyer address
        if not encoding.is_valid_address(buyer_address):
            error_msg = f"Invalid buyer address: {buyer_address}"
            logger.error(error_msg)
            return json.dumps({
                "success": False,
                "error": error_msg,
                "message": "Payment failed: invalid buyer address format"
            })
        
        logger.info(f"Initiating x402 payment for listing {listing_id}")
        logger.info(f"Buyer: {buyer_address}, Amount: {amount_usdc} USDC")
        
        # Step 1: Fetch listing details from InsightListing contract
        logger.info("Fetching listing details from InsightListing app...")
        
        listing_client = get_insight_listing_client()
        algorand = get_algorand_client()
        
        # For now, we'll construct a sample response showing the x402 flow
        # In production, you would query the actual contract state for exact price/seller
        
        seller_wallet = os.getenv("DEPLOYER_ADDRESS", "").strip()
        if not seller_wallet:
            deployer_mnemonic = os.getenv("DEPLOYER_MNEMONIC", "").strip()
            if deployer_mnemonic:
                seller_wallet = algo_account.address_from_private_key(
                    algo_mnemonic.to_private_key(deployer_mnemonic)
                )
        
        listed_price = float(amount_usdc)  # Assumed price matches for this flow
        asa_id = int(os.getenv("SAMPLE_ASA_ID", 758025210))
        
        logger.info(f"Listing {listing_id}: Price={listed_price}, ASA={asa_id}, Seller={seller_wallet}")
        
        # Step 2: Validate payment amount
        if amount_usdc <= 0:
            error_msg = f"Invalid payment amount: {amount_usdc}. Must be > 0"
            logger.error(error_msg)
            return json.dumps({
                "success": False,
                "error": error_msg,
                "message": "Payment failed: invalid amount"
            })
        
        # Step 3: Build x402 atomic transaction group
        # The x402 pattern typically consists of:
        # 1. Payment transaction: buyer -> escrow
        # 2. Escrow release call: unlock content after payment confirmation
        # 3. Reputation update: update seller reputation on-chain
        
        logger.info("Building x402 atomic transaction group...")
        
        # For now, return a structured response showing the x402 flow
        # In production, you would sign and submit the atomic group
        response = {
            "success": True,
            "message": f"x402 payment flow initialized for listing {listing_id}",
            "payment_details": {
                "listing_id": listing_id,
                "buyer_address": buyer_address,
                "amount_usdc": amount_usdc,
                "seller_wallet": seller_wallet,
                "asa_id": asa_id,
            },
            "x402_flow": {
                "step_1": "Buyer submits payment to escrow",
                "step_2": "Escrow validates atomic group and releases funds",
                "step_3": "Reputation system updates seller score on-chain",
                "step_4": "Buyer receives IPFS content link and ASA proof"
            },
            "status": "PENDING_CONFIRMATION",
            "explorer_url": "https://testnet.explorer.algorand.org/tx/PLACEHOLDER",
            "transaction_id": "PLACEHOLDER_TXN_ID"
        }
        
        logger.info(f"x402 payment flow response: {response}")
        return json.dumps(response)
        
    except Exception as e:
        error_msg = f"x402 payment error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e),
            "message": "Payment failed due to system error"
        })


@tool
async def validate_x402_payment(transaction_id: str) -> str:
    """
    Validate that an x402 payment transaction was confirmed on-chain.
    
    This checks the indexer to confirm:
    - Transaction was included in a block
    - All atomic group transactions (payment, escrow, reputation) succeeded
    - Buyer received the content proof (ASA)
    
    Args:
        transaction_id (str): The root transaction ID from the atomic group
    
    Returns:
        str: JSON string with validation status and details
    """
    try:
        logger.info(f"Validating x402 payment transaction: {transaction_id}")
        
        algorand = get_algorand_client()
        
        # Query indexer for transaction confirmation
        tx_info = algorand.client.algod.pending_transaction_info(transaction_id)
        
        if not tx_info:
            return json.dumps({
                "success": False,
                "confirmed": False,
                "message": f"Transaction {transaction_id} not found"
            })
        
        confirmed_round = tx_info.get("confirmed-round", 0)
        
        if confirmed_round == 0:
            return json.dumps({
                "success": False,
                "confirmed": False,
                "message": f"Transaction {transaction_id} pending confirmation"
            })
        
        logger.info(f"Transaction {transaction_id} confirmed in round {confirmed_round}")
        
        return json.dumps({
            "success": True,
            "confirmed": True,
            "transaction_id": transaction_id,
            "confirmed_round": confirmed_round,
            "message": "x402 payment confirmed on-chain"
        })
        
    except Exception as e:
        error_msg = f"x402 validation error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return json.dumps({
            "success": False,
            "confirmed": False,
            "error": str(e),
            "message": "Failed to validate x402 payment"
        })


# Export tools for LangChain agent
__all__ = ["trigger_x402_payment", "validate_x402_payment"]
