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
import requests
from algokit_utils import AlgorandClient
from backend.utils.error_handler import ipfs_down


PINATA_BASE_URL = "https://api.pinata.cloud"
PIN_FILE_ENDPOINT = f"{PINATA_BASE_URL}/pinning/pinFileToIPFS"
PIN_JSON_ENDPOINT = f"{PINATA_BASE_URL}/pinning/pinJSONToIPFS"
UNPIN_ENDPOINT = f"{PINATA_BASE_URL}/pinning/unpin"
_CID_TEXT_CACHE: dict[str, str] = {}
logger = logging.getLogger(__name__)


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


def upload_text_content(content: str, name: str = "insight.txt") -> dict[str, Any]:
    """Upload plain-text content to IPFS via Pinata.
    
    Purpose: Persistence layer for insight text. Returns CID + full Pinata response.
    Used by: /list endpoint to store insights before on-chain listing creation.
    Returns: Pinata API response payload, including IpfsHash (CID) when successful.
    """
    files = {
        "file": (name, content.encode("utf-8"), "text/plain"),
    }
    response = requests.post(
        PIN_FILE_ENDPOINT,
        headers=_get_pinata_headers(),
        files=files,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def upload_json_content(payload: dict[str, Any]) -> dict[str, Any]:
    """Upload JSON payload to Pinata and return pinning response.

    Input: payload dictionary.
    Output: Pinata response including IpfsHash on success.
    Micropayment role: optional metadata channel for auxiliary flow artifacts.
    """
    response = requests.post(
        PIN_JSON_ENDPOINT,
        headers=_get_pinata_headers(),
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def unpin_cid(cid: str) -> None:
    """Remove a CID from Pinata pinset.

    Input: CID string.
    Output: none (raises on request failure).
    Micropayment role: cleanup helper for test artifacts and stale demo uploads.
    """
    response = requests.delete(
        f"{UNPIN_ENDPOINT}/{cid}",
        headers=_get_pinata_headers(),
        timeout=30,
    )
    response.raise_for_status()


async def upload_insight_to_ipfs(text: str, filename: str = "insight.txt") -> str:
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

    try:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await asyncio.to_thread(
                    requests.post,
                    PIN_FILE_ENDPOINT,
                    headers=_get_pinata_headers(),
                    files=files,
                    data=data,
                    timeout=30,
                )

                if response.status_code == 429:
                    if attempt < 2:
                        await asyncio.sleep(3)
                        continue
                    raise IPFSUploadError(ipfs_down(logger, "Pinata rate limit after retries"))

                response.raise_for_status()

                payload = response.json()
                cid = str(payload.get("IpfsHash", "")).strip()
                if not cid:
                    raise RuntimeError("Pinata response missing IpfsHash")
                if not cid.startswith("Qm"):
                    raise RuntimeError(f"Expected CID starting with 'Qm', got: {cid}")
                _CID_TEXT_CACHE[cid] = text
                return cid
            except requests.exceptions.Timeout as err:
                logger.error("IPFS upload timeout | attempt=%s error=%s", attempt + 1, err)
                last_error = err
                if attempt < 2:
                    await asyncio.sleep(3)
                    continue
            except requests.exceptions.HTTPError as err:
                logger.error("IPFS upload HTTP error | attempt=%s error=%s", attempt + 1, err)
                last_error = err
                status_code = err.response.status_code if err.response is not None else None
                if status_code == 429 and attempt < 2:
                    await asyncio.sleep(3)
                    continue
                break
            except requests.exceptions.RequestException as err:
                logger.error("IPFS upload request error | attempt=%s error=%s", attempt + 1, err)
                last_error = err
                break
            except TimeoutError as err:
                logger.error("IPFS upload TimeoutError | attempt=%s error=%s", attempt + 1, err)
                last_error = err
                break
            except IPFSUploadError:
                raise
            except Exception as err:
                logger.error("IPFS upload unexpected error | attempt=%s error=%s", attempt + 1, err)
                last_error = err
                break

        raise IPFSUploadError(ipfs_down(logger, str(last_error) if last_error else None)) from last_error
    except requests.exceptions.RequestException as err:
        logger.error("IPFS upload request exception | error=%s", err)
        raise IPFSUploadError(ipfs_down(logger, str(err))) from err
    except TimeoutError as err:
        logger.error("IPFS upload timeout exception | error=%s", err)
        raise IPFSUploadError(ipfs_down(logger, str(err))) from err
    except IPFSUploadError as err:
        logger.error("IPFS upload failed | error=%s", err)
        raise


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

    try:
        last_error: Exception | None = None
        for url in gateways:
            try:
                response = await asyncio.to_thread(
                    requests.get,
                    url,
                    headers=headers,
                    timeout=30,
                )
                response.raise_for_status()
                text = response.text
                _CID_TEXT_CACHE[cid] = text
                return text
            except requests.exceptions.RequestException as err:
                logger.error("IPFS fetch request error | url=%s error=%s", url, err)
                last_error = err
            except TimeoutError as err:
                logger.error("IPFS fetch TimeoutError | url=%s error=%s", url, err)
                last_error = err
            except Exception as err:
                logger.error("IPFS fetch unexpected error | url=%s error=%s", url, err)
                last_error = err

        raise IPFSUploadError(ipfs_down(logger, str(last_error) if last_error else None)) from last_error
    except requests.exceptions.RequestException as err:
        logger.error("IPFS fetch request exception | cid=%s error=%s", cid, err)
        raise IPFSUploadError(ipfs_down(logger, str(err))) from err
    except TimeoutError as err:
        logger.error("IPFS fetch timeout exception | cid=%s error=%s", cid, err)
        raise IPFSUploadError(ipfs_down(logger, str(err))) from err
    except IPFSUploadError as err:
        logger.error("IPFS fetch failed | cid=%s error=%s", cid, err)
        raise


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
    if not mnemonic_for_signing:
        raise ListingStoreError("No signing mnemonic configured for listing transaction")

    private_key = algosdk.mnemonic.to_private_key(mnemonic_for_signing)
    derived_address = algosdk.account.address_from_private_key(private_key)
    if derived_address != seller_address:
        raise ListingStoreError(
            "Signer mnemonic does not match seller address"
        )

    listing_price = price if price is not None else int(os.getenv("DEFAULT_LISTING_PRICE", "1000000"))

    try:
        insight_client_cls = _load_insight_listing_client_class()
        algorand = AlgorandClient.from_environment()
        signer = algorand.account.from_mnemonic(
            mnemonic=mnemonic_for_signing,
            sender=seller_address,
        )
        algorand.set_default_signer(signer)

        app_client = insight_client_cls(
            algorand=algorand,
            app_id=listing_app_id,
            default_sender=signer.address,
        )
        result = app_client.send.create_listing((listing_price, seller_address, cid))
        if result.abi_return is None:
            raise ListingStoreError("Listing call returned no ABI value")
        listing_id = int(result.abi_return)

        listing = app_client.state.box.listings.get_value(listing_id)
        if listing is None:
            raise ListingStoreError("Listing was created but could not be read from state")

        asa_id = int(listing.asa_id)
        return listing_id, asa_id
    except ListingStoreError:
        raise
    except Exception as err:
        detail = str(err).strip() or err.__class__.__name__
        raise ListingStoreError(
            f"Could not link IPFS CID to listing on-chain: {detail}"
        ) from err
