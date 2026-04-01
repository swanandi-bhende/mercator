"""Wrapper module exposing the generated InsightListing client class."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_project_root = Path(__file__).resolve().parents[1]
_client_path = _project_root / (
    "backend/contracts/insight_listing/smart_contracts/artifacts/"
    "insight_listing/insight_listing_client.py"
)

if not _client_path.exists():
    raise ImportError(
        "InsightListing client artifact not found. Build the contract first."
    )

_spec = importlib.util.spec_from_file_location(
    "contracts_insight_listing_client", _client_path
)
if _spec is None or _spec.loader is None:
    raise ImportError("Could not load InsightListing client module")

_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

InsightListingClient = _module.InsightListingClient

__all__ = ["InsightListingClient"]
