from __future__ import annotations

from datetime import datetime
import uuid
from typing import Dict, Any


def generate_request_id() -> str:
    return str(uuid.uuid4())


def success_response(data: Dict[str, Any], request_id: str) -> Dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "error": None,
        "request_id": request_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


def error_response(code: str, message: str, request_id: str, details: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "success": False,
        "data": None,
        "error": {"code": code, "message": message, "details": details or {}},
        "request_id": request_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
