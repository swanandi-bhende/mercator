"""Backend application entrypoint.

This module prepares reusable imports for upcoming API endpoint integration.
"""

try:
    from utils.ipfs import upload_insight_to_ipfs
except ModuleNotFoundError:
    from backend.utils.ipfs import upload_insight_to_ipfs


__all__ = ["upload_insight_to_ipfs"]
