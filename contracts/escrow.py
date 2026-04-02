"""Wrapper module exposing the generated Escrow client class."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_project_root = Path(__file__).resolve().parents[1]
_client_path = _project_root / (
    "backend/contracts/escrow/smart_contracts/artifacts/"
    "escrow/escrow_client.py"
)

if not _client_path.exists():
    raise ImportError(
        "Escrow client artifact not found. Build the contract first."
    )

_spec = importlib.util.spec_from_file_location(
    "contracts_escrow_client", _client_path
)
if _spec is None or _spec.loader is None:
    raise ImportError("Could not load Escrow client module")

_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

EscrowClient = _module.EscrowClient

__all__ = ["EscrowClient"]