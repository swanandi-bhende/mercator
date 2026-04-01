"""IPFS helper utilities for Pinata uploads and pin management.

This module is the single place for reusable IPFS interactions used by the backend.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

import algosdk
import requests
from algokit_utils import AlgorandClient


PINATA_BASE_URL = "https://api.pinata.cloud"
PIN_FILE_ENDPOINT = f"{PINATA_BASE_URL}/pinning/pinFileToIPFS"
PIN_JSON_ENDPOINT = f"{PINATA_BASE_URL}/pinning/pinJSONToIPFS"
UNPIN_ENDPOINT = f"{PINATA_BASE_URL}/pinning/unpin"


class PinataConfigError(RuntimeError):
    """Raised when required Pinata configuration is missing."""


class IPFSUploadError(RuntimeError):
    """Raised when an insight cannot be stored on IPFS."""


class ListingStoreError(RuntimeError):
    """Raised when a CID cannot be linked to an on-chain listing."""


def _get_pinata_headers() -> dict[str, str]:
    """Build authorization headers for Pinata API calls."""
    jwt = os.getenv("PINATA_JWT", "").strip()
    if not jwt:
        raise PinataConfigError("PINATA_JWT is not set")
    return {"Authorization": f"Bearer {jwt}"}


def upload_text_content(content: str, name: str = "insight.txt") -> dict[str, Any]:
    """Upload plain-text content to IPFS via Pinata.

    Returns the Pinata response payload, including IpfsHash when successful.
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
    """Upload JSON content to IPFS via Pinata.

    Returns the Pinata response payload, including IpfsHash when successful.
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
    """Unpin an existing CID from Pinata."""
    response = requests.delete(
        f"{UNPIN_ENDPOINT}/{cid}",
        headers=_get_pinata_headers(),
        timeout=30,
    )
    response.raise_for_status()


async def upload_insight_to_ipfs(text: str, filename: str = "insight.txt") -> str:
    """Upload insight text to Pinata and return the pinned CID.

    The `pinFileToIPFS` endpoint pins automatically when upload succeeds.
    """
    files = {
        "file": (filename, text.encode("utf-8"), "text/plain"),
    }
    data = {
        "pinataOptions": json.dumps({"cidVersion": 0}),
    }

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
                raise IPFSUploadError(
                    "Could not store insight on IPFS — please try again"
                )

            response.raise_for_status()

            payload = response.json()
            cid = str(payload.get("IpfsHash", "")).strip()
            if not cid:
                raise RuntimeError("Pinata response missing IpfsHash")
            if not cid.startswith("Qm"):
                raise RuntimeError(f"Expected CID starting with 'Qm', got: {cid}")
            return cid
        except requests.exceptions.Timeout as err:
            last_error = err
            if attempt < 2:
                await asyncio.sleep(3)
                continue
        except requests.exceptions.HTTPError as err:
            last_error = err
            status_code = err.response.status_code if err.response is not None else None
            if status_code == 429 and attempt < 2:
                await asyncio.sleep(3)
                continue
            break
        except Exception as err:
            last_error = err
            break

    raise IPFSUploadError(
        "Could not store insight on IPFS — please try again"
    ) from last_error


def _load_insight_listing_client_class() -> type:
    """Load the generated InsightListingClient class from artifact path."""
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
    """Call InsightListing.create_listing and link IPFS CID to on-chain listing.

    Uses the generated InsightListing contract client and configured deployer signer.
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
        raise ListingStoreError(
            "Could not link IPFS CID to listing on-chain"
        ) from err
