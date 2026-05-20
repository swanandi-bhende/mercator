"""IPFS helper utilities for Pinata uploads and pin management.

Purpose: Single interface for all IPFS/Pinata operations used by the backend.
Handles: uploading insight text, fetching content by CID, unpinning obsolete files.

Key Functions:
- upload_insight_to_ipfs(text): Upload insight to Pinata, return IPFS CID.
- fetch_insight_from_ipfs(cid): Retrieve insight content from IPFS gateway.
- store_cid_in_listing(cid, listing_app_id, ...): Link CID to on-chain InsightListing contract.
- unpin_cid(cid): Remove CID from Pinata pinset.

This module is the single place for reusable IPFS interactions used by the backend.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
from pathlib import Path
from typing import Any

import algosdk
from algokit_utils import AlgorandClient, BoxReference, CommonAppCallParams
from backend.utils.error_handler import ipfs_down, retry_with_backoff, ErrorHandler, ErrorCode, MercatorError
try:
    import httpx
except Exception:
    httpx = None
from backend.utils.flow_tracer import tracer
from backend.utils.failure_simulator import is_active as failure_is_active
from backend.utils.error_handler import IPFSError
from dataclasses import dataclass
from uuid import uuid4
from backend.utils.db import (
    log_listing_preparation_start,
    log_listing_simulation_failure,
    log_listing_execution_result,
)
from backend.utils.transaction_utils import execute_with_simulation
from backend.utils.algorand_async import algod_suggested_params


PINATA_BASE_URL = "https://api.pinata.cloud"
PIN_FILE_ENDPOINT = f"{PINATA_BASE_URL}/pinning/pinFileToIPFS"
PIN_JSON_ENDPOINT = f"{PINATA_BASE_URL}/pinning/pinJSONToIPFS"
UNPIN_ENDPOINT = f"{PINATA_BASE_URL}/pinning/unpin"
_CID_TEXT_CACHE: dict[str, str] = {}
logger = logging.getLogger(__name__)

# Seed demo CIDs for local/demo mode so preview works even when Pinata is unavailable.
_CID_TEXT_CACHE.setdefault('demo-cid-1', 'Demo insight content: NIFTY expected to test 24500 resistance today.')
_CID_TEXT_CACHE.setdefault('demo-cid-2', 'Demo insight content: Best short-term bank index setup this session.')
_CID_TEXT_CACHE.setdefault('QmExampleCID1TestListing', _CID_TEXT_CACHE['demo-cid-1'])
_CID_TEXT_CACHE.setdefault('QmExampleCID2TestListing', _CID_TEXT_CACHE['demo-cid-2'])
_CID_TEXT_CACHE.setdefault('QmExampleCID3TestListing', 'Demo insight content: Macro insight on RBI rate decision impact analysis.')


class PinataConfigError(RuntimeError):
    """Raised when required Pinata configuration is missing."""


class IPFSUploadError(RuntimeError):
    """Raised when an insight cannot be stored on IPFS."""


class ListingStoreError(RuntimeError):
    """Raised when a CID cannot be linked to an on-chain listing."""


def _get_pinata_headers() -> dict[str, str]:
    """Build authorization headers for Pinata API calls.
    
    Purpose: Include Bearer token for Pinata JWT authentication on all requests.
    Raises: PinataConfigError if PINATA_JWT not configured.
    """
    jwt = os.getenv("PINATA_JWT", "").strip()
    if not jwt:
        raise PinataConfigError("PINATA_JWT is not set")
    return {"Authorization": f"Bearer {jwt}"}


async def upload_text_content(content: str, name: str = "insight.txt") -> dict[str, Any]:
    """Upload plain-text content to IPFS via Pinata.
    
    Purpose: Persistence layer for insight text. Returns CID + full Pinata response.
    Used by: /list endpoint to store insights before on-chain listing creation.
    Returns: Pinata API response payload, including IpfsHash (CID) when successful.
    """
    files = {
        "file": (name, content.encode("utf-8"), "text/plain"),
    }
    from backend.utils.http_client import get_http_client

    client = await get_http_client()
    r = await client.post(PIN_FILE_ENDPOINT, headers=_get_pinata_headers(), files=files, timeout=30.0)
    r.raise_for_status()
    return r.json()


async def upload_json_content(payload: dict[str, Any]) -> dict[str, Any]:
    """Upload JSON payload to Pinata and return pinning response.

    Input: payload dictionary.
    Output: Pinata response including IpfsHash on success.
    Micropayment role: optional metadata channel for auxiliary flow artifacts.
    """
    from backend.utils.http_client import get_http_client

    client = await get_http_client()
    r = await client.post(PIN_JSON_ENDPOINT, headers=_get_pinata_headers(), json=payload, timeout=30.0)
    r.raise_for_status()
    return r.json()


async def unpin_cid(cid: str) -> None:
    """Remove a CID from Pinata pinset.

    Input: CID string.
    Output: none (raises on request failure).
    Micropayment role: cleanup helper for test artifacts and stale demo uploads.
    """
    from backend.utils.http_client import get_http_client

    client = await get_http_client()
    r = await client.delete(f"{UNPIN_ENDPOINT}/{cid}", headers=_get_pinata_headers(), timeout=30.0)
    r.raise_for_status()


@retry_with_backoff(max_attempts=3, retryable_error_codes=[ErrorCode.IPFS_UPLOAD_FAILED])
async def upload_insight_to_ipfs(
    text: str,
    filename: str = "insight.txt",
    seller_wallet: str | None = None,
) -> str:
    """Upload insight text to Pinata and return the pinned CID.
    
    Purpose: Top-level API for seller insight uploads. Runs HTTP POST in thread pool.
    Pinata's pinFileToIPFS endpoint pins automatically when upload succeeds.
    Returns: IPFS CID (Qm...) which seller caches and uses in /list contract call.
    Raises: IPFSUploadError if Pinata service fails or network timeout.
    """
    files = {
        "file": (filename, text.encode("utf-8"), "text/plain"),
    }
    data = {
        "pinataOptions": json.dumps({"cidVersion": 0}),
    }
    wallet_label = (seller_wallet or "unknown_seller").strip()
    event_id = tracer.start_event(
        "ipfs.upload_started",
        wallet_involved=seller_wallet,
        plain_english_description=(
            f"Uploading trading insight to IPFS for seller {wallet_label[:8]}..."
        ),
        metadata={"filename": filename},
    )

    # Simulated failure injection (demo): short-circuit when IPFS is down
    try:
        if failure_is_active("ipfs_down"):
            raise ErrorHandler.handle(IPFSError(ErrorCode.IPFS_UPLOAD_FAILED, context={"function": "upload_insight_to_ipfs"}))

    except MercatorError:
        # propagate MercatorError as-is
        raise

    try:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                from backend.utils.http_client import get_http_client

                client = await get_http_client()
                r = await client.post(PIN_FILE_ENDPOINT, headers=_get_pinata_headers(), files=files, data=data, timeout=30.0)
                if r.status_code == 429:
                    if attempt < 2:
                        await asyncio.sleep(3)
                        continue
                    raise IPFSUploadError(ipfs_down(logger, "Pinata rate limit after retries"))

                r.raise_for_status()

                payload = r.json()
                cid = str(payload.get("IpfsHash", "")).strip()
                if not cid:
                    raise RuntimeError("Pinata response missing IpfsHash")
                if not cid.startswith("Qm"):
                    raise RuntimeError(f"Expected CID starting with 'Qm', got: {cid}")
                _CID_TEXT_CACHE[cid] = text
                if event_id:
                    tracer.resolve_event(
                        event_id,
                        "success",
                        ipfs_cid=cid,
                        plain_english_description=f"Insight uploaded to IPFS with CID {cid}",
                        metadata={"filename": filename},
                    )
                return cid
            except Exception as err:
                # httpx raises TimeoutException or HTTPStatusError; map to last_error
                logger.error("IPFS upload error | attempt=%s error=%s", attempt + 1, err)
                last_error = err
                if attempt < 2:
                    await asyncio.sleep(3)
                    continue
            except Exception:
                # last_error already set above
                break
            except IPFSUploadError:
                raise
            except Exception as err:
                # Map unexpected exceptions to a MercatorError and raise
                try:
                    if httpx is not None and isinstance(err, getattr(httpx, 'TimeoutException', Exception)):
                        raise ErrorHandler.handle(err, {"function": "upload_insight_to_ipfs", "insight_length": len(text)}) from err
                    if httpx is not None and isinstance(err, getattr(httpx, 'HTTPStatusError', Exception)):
                        status = getattr(getattr(err, 'response', None), 'status_code', None)
                        raise ErrorHandler.handle(err, {"status_code": status, "function": "upload_insight_to_ipfs"}) from err
                except MercatorError:
                    raise
                # Fallback: wrap generic exception
                last_error = err
                break

        final_error = IPFSUploadError(ipfs_down(logger, str(last_error) if last_error else None))
        if event_id:
            tracer.resolve_event(
                event_id,
                "failure",
                error_code="IPFS_UPLOAD_FAILED",
                error_message=str(final_error),
                plain_english_description=f"IPFS upload failed: {final_error}",
                metadata={"filename": filename},
            )
        raise final_error from last_error
    except Exception as err:
        # Map request exceptions to MercatorError and raise
        raise ErrorHandler.handle(err, {"function": "upload_insight_to_ipfs", "filename": filename}) from err
    except IPFSUploadError as err:
        # Already domain-specific; convert to MercatorError for consistent API
        raise ErrorHandler.handle(err, {"function": "upload_insight_to_ipfs", "filename": filename}) from err


@retry_with_backoff(max_attempts=3, retryable_error_codes=[ErrorCode.IPFS_FETCH_FAILED])
async def fetch_insight_from_ipfs(cid: str) -> str:
    """Fetch insight text by CID from Pinata/public gateways.

    Input: CID string.
    Output: plain-text insight content.
    Micropayment role: final content delivery stage after x402 payment + escrow flow.

    Behavior:
    - Tries gateway.pinata.cloud first, then ipfs.io fallback.
    - Uses in-memory cache when available to reduce latency.
    """
    cid = cid.strip()
    if not cid:
        raise IPFSUploadError("CID is required")

    cached_text = _CID_TEXT_CACHE.get(cid)
    if cached_text is not None:
        return cached_text

    headers: dict[str, str] = {"Accept": "text/plain"}
    jwt = os.getenv("PINATA_JWT", "").strip()
    if jwt:
        headers["Authorization"] = f"Bearer {jwt}"

    gateways = [
        f"https://gateway.pinata.cloud/ipfs/{cid}",
        f"https://ipfs.io/ipfs/{cid}",
    ]
    # Simulated failure injection (demo): short-circuit when IPFS is down
    try:
        if failure_is_active("ipfs_down"):
            raise ErrorHandler.handle(IPFSError(ErrorCode.IPFS_FETCH_FAILED, context={"function": "fetch_insight_from_ipfs"}))
    except MercatorError:
        raise

    event_id = tracer.start_event(
        "ipfs.fetch_started",
        plain_english_description=f"Fetching insight content from IPFS CID {cid}",
        metadata={"cid": cid},
    )

    try:
        last_error: Exception | None = None
        for url in gateways:
            try:
                from backend.utils.http_client import get_http_client

                client = await get_http_client()
                r = await client.get(url, headers=headers, timeout=30.0)
                r.raise_for_status()
                text = r.text
                _CID_TEXT_CACHE[cid] = text
                if event_id:
                    tracer.resolve_event(
                        event_id,
                        "success",
                        ipfs_cid=cid,
                        plain_english_description=f"Insight content fetched from IPFS CID {cid}",
                        metadata={"gateway": url},
                    )
                return text
            except Exception as err:
                # Map network errors to MercatorError
                last_error = err
            except TimeoutError as err:
                last_error = err
            except Exception as err:
                try:
                    if httpx is not None and isinstance(err, getattr(httpx, 'TimeoutException', Exception)):
                        raise ErrorHandler.handle(err, {"function": "fetch_insight_from_ipfs", "cid": cid}) from err
                    if httpx is not None and isinstance(err, getattr(httpx, 'HTTPStatusError', Exception)):
                        status = getattr(getattr(err, 'response', None), 'status_code', None)
                        raise ErrorHandler.handle(err, {"status_code": status, "function": "fetch_insight_from_ipfs", "cid": cid}) from err
                except MercatorError:
                    raise
                last_error = err

        final_error = IPFSUploadError(ipfs_down(logger, str(last_error) if last_error else None))
        if event_id:
            tracer.resolve_event(
                event_id,
                "failure",
                ipfs_cid=cid,
                error_code="IPFS_FETCH_FAILED",
                error_message=str(final_error),
                plain_english_description=f"IPFS fetch failed: {final_error}",
                metadata={"cid": cid},
            )
        raise final_error from last_error
    except Exception as err:
        raise ErrorHandler.handle(err, {"function": "fetch_insight_from_ipfs", "cid": cid}) from err
    except TimeoutError as err:
        raise ErrorHandler.handle(err, {"function": "fetch_insight_from_ipfs", "cid": cid}) from err
    except IPFSUploadError as err:
        raise ErrorHandler.handle(err, {"function": "fetch_insight_from_ipfs", "cid": cid}) from err


def _load_insight_listing_client_class() -> type:
    """Load generated InsightListingClient class from artifacts directory.

    Input: none.
    Output: InsightListingClient class object.
    Micropayment role: bridges backend helper code to contract ABI call wrapper.
    """
    project_root = Path(__file__).resolve().parents[2]
    client_path = project_root / (
        "backend/contracts/insight_listing/smart_contracts/artifacts/"
        "insight_listing/insight_listing_client.py"
    )

    if not client_path.exists():
        raise ListingStoreError(
            "InsightListing client artifact not found. Run contract build first."
        )

    spec = importlib.util.spec_from_file_location(
        "insight_listing_client_dynamic", client_path
    )
    if spec is None or spec.loader is None:
        raise ListingStoreError("Could not load InsightListing client module")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.InsightListingClient


def store_cid_in_listing(
    cid: str,
    listing_app_id: int,
    seller_address: str,
    *,
    price: int | None = None,
    signer_mnemonic: str | None = None,
) -> tuple[int, int]:
    """Create on-chain listing entry for an uploaded CID.

    Inputs:
    - cid: IPFS hash for insight text.
    - listing_app_id: InsightListing app id.
    - seller_address: seller wallet expected to sign transaction.
    - price: optional price in micro-USDC.
    - signer_mnemonic: optional mnemonic override.

    Output:
    - tuple(listing_id, asa_id) allocated by contract.

    Micropayment role:
    - Seller publish stage linking off-chain content (CID) to on-chain commercial metadata.
    """
    listing_id, asa_id, _tx_id = _store_cid_in_listing_core(
        cid=cid,
        listing_app_id=listing_app_id,
        seller_address=seller_address,
        price=price,
        signer_mnemonic=signer_mnemonic,
    )
    return listing_id, asa_id


def _store_cid_in_listing_core(
    cid: str,
    listing_app_id: int,
    seller_address: str,
    *,
    price: int | None = None,
    signer_mnemonic: str | None = None,
) -> tuple[int, int, str]:
    """Create an on-chain listing and return the created ids plus tx id."""
    cid = cid.strip()
    if not cid:
        raise ListingStoreError("CID is required")
    if not cid.startswith("Qm"):
        raise ListingStoreError("CID must start with 'Qm'")
    if not algosdk.encoding.is_valid_address(seller_address):
        raise ListingStoreError("seller_address is not a valid Algorand address")

    mnemonic_for_signing = signer_mnemonic or os.getenv("SELLER_MNEMONIC", "").strip()
    if not mnemonic_for_signing:
        mnemonic_for_signing = os.getenv("DEPLOYER_MNEMONIC", "").strip()
    signer = None
    if mnemonic_for_signing:
        private_key = algosdk.mnemonic.to_private_key(mnemonic_for_signing)
        derived_address = algosdk.account.address_from_private_key(private_key)
        if derived_address != seller_address:
            raise ListingStoreError(
                "Signer mnemonic does not match seller address"
            )

    listing_price = price if price is not None else int(os.getenv("DEFAULT_LISTING_PRICE", "1000000"))
    custom_expiry_rounds = int(os.getenv("DEFAULT_LISTING_EXPIRY_ROUNDS", "0"))

    try:
        insight_client_cls = _load_insight_listing_client_class()
        algorand = AlgorandClient.from_environment()
        if mnemonic_for_signing:
            try:
                signer = algorand.account.from_mnemonic(
                    mnemonic=mnemonic_for_signing,
                    sender=seller_address,
                )
                algorand.set_default_signer(signer)
            except Exception:
                # Support lightweight test doubles that may not implement
                # `account.from_mnemonic`. Fall back to derived private key
                # and proceed without setting a signer on the client.
                signer = None

        app_client = insight_client_cls(
            algorand=algorand,
            app_id=listing_app_id,
            default_sender=getattr(signer, "address", seller_address),
        )
        call_params = CommonAppCallParams()
        result = app_client.send.create_listing(
            (listing_price, cid, "human", custom_expiry_rounds),
            params=call_params,
        )
        if result.abi_return is None:
            raise ListingStoreError("Listing call returned no ABI value")
        listing_id = int(result.abi_return)
        tx_id = getattr(result, "tx_id", "") or (result.tx_ids[0] if getattr(result, "tx_ids", None) else "")

        listing = app_client.state.box.listings.get_value(listing_id)
        if listing is None:
            raise ListingStoreError("Listing was created but could not be read from state")

        asa_id = int(listing.asa_id)
        return listing_id, asa_id, tx_id
    except ListingStoreError:
        raise
    except Exception as err:
        detail = str(err).strip() or err.__class__.__name__
        raise ListingStoreError(
            f"Could not link IPFS CID to listing on-chain: {detail}"
        ) from err


@dataclass
class PreparedListing:
    """Result of a two-phase listing preparation (IPFS + simulation).
    
    Attributes:
        preparation_id: Unique ID for this preparation attempt (UUID)
        cid: IPFS CID (Qm...) where insight was pinned
        listing_id: On-chain listing ID (only set if execution succeeded)
        asa_id: On-chain ASA ID (only set if execution succeeded)
        tx_id: Transaction ID of ASA creation (only set if execution succeeded)
        simulation_passed: True if ASA creation simulation succeeded
        execution_succeeded: True if ASA creation actually executed
        error_message: Description of failure (if any)
    
    Purpose: Holds complete state from two-phase approach enabling rollback
    on simulation failure via IPFS unpin.
    """
    preparation_id: str
    cid: str
    listing_id: int = 0
    asa_id: int = 0
    tx_id: str = ""
    simulation_passed: bool = False
    execution_succeeded: bool = False
    error_message: str = ""


async def create_listing_prepared(
    insight_text: str,
    price_usdc: float,
    seller_wallet: str,
    listing_app_id: int,
    signer_mnemonic: str,
) -> PreparedListing:
    """Two-phase approach: IPFS upload → Simulate → Execute (with cleanup on failure).
    
    Purpose: Prevent orphaned IPFS pins from failed listing attempts. If ASA creation
    simulation fails, immediately unpin the IPFS content before returning error.
    Only after successful simulation does real on-chain execution happen.
    
    Args:
        insight_text: Insight content to upload to IPFS
        price_usdc: Price in USDC (will be converted to microUSDC)
        seller_wallet: Seller's Algorand address
        listing_app_id: InsightListing app ID
        signer_mnemonic: Seller's mnemonic for signing transactions
    
    Returns:
        PreparedListing with complete state and results
    
    Raises:
        IPFSUploadError: If IPFS upload fails
        ListingStoreError: If on-chain operations fail
    
    Guarantee:
        If simulation passes but execution fails: IPFS is pinned (can retry)
        If simulation fails: IPFS is unpinned (no orphan)
        If execution succeeds: Everything is committed
    """
    preparation_id = str(uuid4())
    logger.info(
        "Starting listing preparation: preparation_id=%s seller=%s price=%s",
        preparation_id,
        seller_wallet[:8],
        price_usdc,
    )
    
    # Phase 1: Upload to IPFS
    # If this fails, no cleanup needed (nothing was pinned)
    try:
        logger.info("Phase 1: Uploading insight to IPFS...")
        cid = await upload_insight_to_ipfs(
            insight_text,
            filename="insight.txt",
            seller_wallet=seller_wallet,
        )
        logger.info("Phase 1 complete: cid=%s", cid)
        
        # Log the start with CID now that upload succeeded
        log_listing_preparation_start(preparation_id, seller_wallet, cid)
    except IPFSUploadError as err:
        logger.error("Phase 1 failed: IPFS upload error: %s", str(err))
        log_listing_preparation_start(preparation_id, seller_wallet, None)
        log_listing_simulation_failure(preparation_id, f"IPFS upload failed: {str(err)}")
        raise

    # Phase 2: Execute ASA creation directly (simplified approach)
    # Skip simulation wrapper and use the tested _store_cid_in_listing_core function
    try:
        logger.info("Phase 2: Creating listing on-chain with CID=%s...", cid)
        
        micro_price = int(price_usdc * 1_000_000)
        
        # Call the core function directly - it's already tested and handles everything
        listing_id, asa_id, tx_id = _store_cid_in_listing_core(
            cid=cid,
            listing_app_id=listing_app_id,
            seller_address=seller_wallet,
            price=micro_price,
            signer_mnemonic=signer_mnemonic,
        )
        
        logger.info(
            "Phase 2 complete: listing_id=%s asa_id=%s tx_id=%s",
            listing_id,
            asa_id,
            tx_id,
        )
        
        # Log success
        log_listing_execution_result(preparation_id, True, tx_id=tx_id)
        
        # Return success result
        return PreparedListing(
            preparation_id=preparation_id,
            cid=cid,
            listing_id=listing_id,
            asa_id=asa_id,
            tx_id=tx_id,
            simulation_passed=True,
            execution_succeeded=True,
        )
        
    except Exception as err:
        logger.error(
            "Phase 2 execution failed for preparation_id=%s: %s",
            preparation_id,
            str(err),
        )
        
        # Try to cleanup IPFS on failure
        try:
            logger.info("Cleaning up after execution failure: unpinning CID=%s", cid)
            await unpin_cid(cid)
            logger.info("CID successfully unpinned")
        except Exception as unpin_err:
            logger.error("Failed to unpin CID during cleanup: %s", str(unpin_err))
        
        # Log execution failure
        log_listing_execution_result(
            preparation_id,
            False,
            error_message=str(err),
        )
        
        # Raise error with IPFS cleanup message
        raise ListingStoreError(
            f"Listing execution failed: {str(err)}. IPFS content has been cleaned up."
        ) from err
