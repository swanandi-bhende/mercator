from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

try:
    import httpx
except Exception:  # pragma: no cover - optional dependency for some runtime environments
    httpx = None

try:
    import tenacity
except Exception:  # pragma: no cover - tenacity should be a dependency where used
    tenacity = None

try:
    from pydantic import ValidationError as PydanticValidationError
except Exception:
    PydanticValidationError = None

try:
    from algosdk.error import AlgodHTTPError
except Exception:
    AlgodHTTPError = None

logger = logging.getLogger("mercator.errors")


# ERROR_REGISTRY: centralised user-facing messages + recovery suggestions.
ERROR_REGISTRY: Dict[str, Dict[str, str]] = {
    # Group 1: IPFS errors
    "IPFS_UPLOAD_FAILED": {
        "user_message": "We couldn't store your insight on IPFS right now",
        "recovery_suggestion": "IPFS may be temporarily slow. Your insight was not listed. Please try again in 30 seconds.",
    },
    "IPFS_FETCH_FAILED": {
        "user_message": "We couldn't retrieve the insight content",
        "recovery_suggestion": "The insight content may be temporarily unavailable. Please try again or contact the seller.",
    },
    "IPFS_PIN_FAILED": {
        "user_message": "Your insight was uploaded but could not be pinned",
        "recovery_suggestion": "Pinning failed — the content may disappear soon. Contact support.",
    },

    # Group 2: Algorand network errors
    "ALGOD_TIMEOUT": {
        "user_message": "The Algorand network is responding slowly",
        "recovery_suggestion": "TestNet may be congested. Your transaction was not submitted. Please retry.",
    },
    "ALGOD_INSUFFICIENT_FEES": {
        "user_message": "Transaction fee was too low",
        "recovery_suggestion": "This is a system error — please try again. If it persists, contact support.",
    },
    "ALGOD_TRANSACTION_REJECTED": {
        "user_message": "Your transaction was rejected by the network",
        "recovery_suggestion": "Check your wallet balance and try again.",
    },
    "ALGOD_CONTRACT_REVERT": {
        "user_message": "The smart contract rejected this operation",
        "recovery_suggestion": "See the specific reason below.",
    },

    # Group 3: Payment errors
    "PAYMENT_INSUFFICIENT_BALANCE": {
        "user_message": "Your wallet doesn't have enough USDC",
        "recovery_suggestion": "Add more USDC to your wallet. You need at least {amount} USDC.",
    },
    "PAYMENT_SIMULATION_FAILED": {
        "user_message": "Payment simulation failed before broadcast",
        "recovery_suggestion": "No funds were spent. Please check your wallet balance and try again.",
    },
    "PAYMENT_BROADCAST_FAILED": {
        "user_message": "Payment was submitted but confirmation timed out",
        "recovery_suggestion": "Check the Algorand explorer for your wallet address to see if the transaction confirmed.",
    },
    "X402_REJECTED": {
        "user_message": "The x402 payment protocol rejected this transaction",
        "recovery_suggestion": "Please retry. If this persists, your wallet may need to opt into the USDC asset.",
    },

    # Group 4: Agent errors
    "GEMINI_RATE_LIMIT": {
        "user_message": "Our AI is temporarily busy",
        "recovery_suggestion": "Please wait 30 seconds and try again.",
    },
    "GEMINI_PARSE_FAILURE": {
        "user_message": "The AI produced an unexpected response",
        "recovery_suggestion": "This is a temporary issue. Retry the search.",
    },
    "AGENT_NO_RESULTS": {
        "user_message": "No listings matched your search criteria",
        "recovery_suggestion": "Try a broader query or lower the minimum reputation threshold.",
    },
    "AGENT_EVALUATION_TIMEOUT": {
        "user_message": "The AI took too long to evaluate this listing",
        "recovery_suggestion": "Please retry. If it persists, try a different listing.",
    },

    "MARKET_DATA_UNAVAILABLE": {
        "user_message": "Market data is currently unavailable",
        "recovery_suggestion": "Market data provider may be temporarily down. Please try again later.",
    },

    # Group 5: Contract state errors
    "LISTING_EXPIRED": {
        "user_message": "This listing has expired",
        "recovery_suggestion": "Search for a more recent listing on the same topic.",
    },
    "LISTING_ALREADY_SOLD": {
        "user_message": "This listing was already purchased by another buyer",
        "recovery_suggestion": "Search for a similar listing — the seller may have published more.",
    },
    "LISTING_NOT_FOUND": {
        "user_message": "This listing no longer exists",
        "recovery_suggestion": "Return to the search results and choose a different listing.",
    },
    "UNREGISTERED_AGENT": {
        "user_message": "This wallet is not registered as a verified agent",
        "recovery_suggestion": "The agent must call AgentRegistry.register() before transacting.",
    },
    "REPUTATION_BELOW_THRESHOLD": {
        "user_message": "This seller's trust score is below our minimum",
        "recovery_suggestion": "Try a listing from a higher-reputation seller.",
    },
    "SUBSCRIPTION_EXPIRED": {
        "user_message": "Your subscription has expired",
        "recovery_suggestion": "Renew your subscription to continue accessing unlimited insights.",
    },

    # Group 6: System errors
    "DATABASE_ERROR": {
        "user_message": "A database error occurred",
        "recovery_suggestion": "This is a system error. Please try again.",
    },
    "VALIDATION_ERROR": {
        "user_message": "The provided data is invalid",
        "recovery_suggestion": "See the specific field error below.",
    },
    "UNKNOWN_ERROR": {
        "user_message": "An unexpected error occurred",
        "recovery_suggestion": "Please try again. If it persists, contact support.",
    },
}


class ErrorCode(str, Enum):
    IPFS_UPLOAD_FAILED = "IPFS_UPLOAD_FAILED"
    IPFS_FETCH_FAILED = "IPFS_FETCH_FAILED"
    IPFS_PIN_FAILED = "IPFS_PIN_FAILED"

    ALGOD_TIMEOUT = "ALGOD_TIMEOUT"
    ALGOD_INSUFFICIENT_FEES = "ALGOD_INSUFFICIENT_FEES"
    ALGOD_TRANSACTION_REJECTED = "ALGOD_TRANSACTION_REJECTED"
    ALGOD_CONTRACT_REVERT = "ALGOD_CONTRACT_REVERT"

    PAYMENT_INSUFFICIENT_BALANCE = "PAYMENT_INSUFFICIENT_BALANCE"
    PAYMENT_SIMULATION_FAILED = "PAYMENT_SIMULATION_FAILED"
    PAYMENT_BROADCAST_FAILED = "PAYMENT_BROADCAST_FAILED"
    X402_REJECTED = "X402_REJECTED"

    GEMINI_RATE_LIMIT = "GEMINI_RATE_LIMIT"
    GEMINI_PARSE_FAILURE = "GEMINI_PARSE_FAILURE"
    AGENT_NO_RESULTS = "AGENT_NO_RESULTS"
    AGENT_EVALUATION_TIMEOUT = "AGENT_EVALUATION_TIMEOUT"

    LISTING_EXPIRED = "LISTING_EXPIRED"
    LISTING_ALREADY_SOLD = "LISTING_ALREADY_SOLD"
    LISTING_NOT_FOUND = "LISTING_NOT_FOUND"
    UNREGISTERED_AGENT = "UNREGISTERED_AGENT"
    REPUTATION_BELOW_THRESHOLD = "REPUTATION_BELOW_THRESHOLD"
    SUBSCRIPTION_EXPIRED = "SUBSCRIPTION_EXPIRED"
    MARKET_DATA_UNAVAILABLE = "MARKET_DATA_UNAVAILABLE"

    DATABASE_ERROR = "DATABASE_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class MercatorError(Exception):
    def __init__(self, code: ErrorCode, context: Optional[Dict[str, Any]] = None, original_exception: Optional[Exception] = None):
        self.code = code
        self.user_message = ERROR_REGISTRY.get(code.value, {}).get("user_message", "An error occurred")
        self.recovery_suggestion = ERROR_REGISTRY.get(code.value, {}).get("recovery_suggestion", "")
        self.context = context or {}
        self.original_exception = original_exception
        self.error_id = str(uuid.uuid4())
        self.occurred_at = datetime.utcnow().isoformat() + "Z"
        super().__init__(f"[{self.code}] {self.user_message}")

    def __str__(self) -> str:
        return f"[{self.code}] {self.user_message}"


class IPFSError(MercatorError):
    pass


class AlgorandError(MercatorError):
    pass


class PaymentError(MercatorError):
    pass


class AgentError(MercatorError):
    pass


class ContractStateError(MercatorError):
    pass


class SystemError(MercatorError):
    pass


def ipfs_down(logger: logging.Logger, reason: Optional[str] = None) -> str:
    msg = f"IPFS downtime: {reason or 'temporary unavailability'}"
    try:
        logger.warning(msg)
    except Exception:
        pass
    return msg


class ErrorHandler:
    @classmethod
    def handle(cls, exception: Exception, context: Optional[Dict[str, Any]] = None) -> MercatorError:
        # If already a MercatorError, log and return unchanged
        if isinstance(exception, MercatorError):
            err = exception
            cls._log_error(err, context)
            return err

        # Ordered mapping: first match wins. Each entry is (predicate, ErrorCode, ErrorSubclass)
        mapping: List[tuple[Callable[[Exception], bool], ErrorCode, type]] = []

        # httpx-specific mappings
        if httpx is not None:
            mapping.append((lambda e: isinstance(e, getattr(httpx, 'TimeoutException', Exception)), ErrorCode.ALGOD_TIMEOUT, AlgorandError))
            mapping.append((lambda e: isinstance(e, getattr(httpx, 'HTTPStatusError', Exception)) and getattr(getattr(e, 'response', None), 'status_code', 0) == 429, ErrorCode.GEMINI_RATE_LIMIT, AgentError))
            mapping.append((lambda e: isinstance(e, getattr(httpx, 'HTTPStatusError', Exception)) and getattr(getattr(e, 'response', None), 'status_code', 0) >= 500, ErrorCode.IPFS_UPLOAD_FAILED, IPFSError))

        # Algod HTTP errors
        if AlgodHTTPError is not None:
            mapping.append((lambda e: isinstance(e, AlgodHTTPError), ErrorCode.ALGOD_TRANSACTION_REJECTED, AlgorandError))

        # JSON parse
        mapping.append((lambda e: isinstance(e, json.JSONDecodeError), ErrorCode.GEMINI_PARSE_FAILURE, AgentError))

        # Pydantic validation
        if PydanticValidationError is not None:
            mapping.append((lambda e: isinstance(e, PydanticValidationError), ErrorCode.VALIDATION_ERROR, SystemError))

        # sqlite
        mapping.append((lambda e: isinstance(e, sqlite3.Error), ErrorCode.DATABASE_ERROR, SystemError))

        # Fallback: unknown
        mapping.append((lambda e: True, ErrorCode.UNKNOWN_ERROR, SystemError))

        selected_code = ErrorCode.UNKNOWN_ERROR
        selected_class = SystemError

        for predicate, code, cls_type in mapping:
            try:
                if predicate(exception):
                    selected_code = code
                    selected_class = cls_type
                    break
            except Exception:
                continue

        err = selected_class(selected_code, context=context or {}, original_exception=exception)
        cls._log_error(err, context)

        # Try to record to tracer if available
        try:
            from backend.utils import flow_tracer as _ft

            tracer = getattr(_ft, "tracer", None)
            if tracer is not None and getattr(tracer, "get_current_session_id", lambda: None)() is not None:
                try:
                    tracer.record("error", "failure", error_code=err.code, error_message=err.user_message)
                except Exception:
                    pass
        except Exception:
            pass

        return err

    @classmethod
    def _log_error(cls, error: MercatorError, context: Optional[Dict[str, Any]] = None) -> None:
        try:
            logger.error(
                error.user_message,
                extra={
                    "error_id": error.error_id,
                    "error_code": error.code,
                    "context": json.dumps(context or {}),
                    "original_exception": str(error.original_exception) if error.original_exception is not None else "",
                    "occurred_at": error.occurred_at,
                },
            )
        except Exception:
            try:
                # best-effort fallback
                logger.error(f"{error.user_message} | {error.error_id} | {error.code}")
            except Exception:
                pass


def retry_with_backoff(
    max_attempts: int = 3,
    min_wait_seconds: float = 2.0,
    max_wait_seconds: float = 30.0,
    retryable_error_codes: Optional[List[ErrorCode]] = None,
) -> Callable:
    if tenacity is None:
        def _noop_decorator(fn):
            return fn

        return _noop_decorator

    retryable_codes = set(retryable_error_codes or [ErrorCode.IPFS_UPLOAD_FAILED, ErrorCode.ALGOD_TIMEOUT, ErrorCode.GEMINI_RATE_LIMIT])

    def _is_retryable_exception(exc: Exception) -> bool:
        try:
            return isinstance(exc, MercatorError) and exc.code in retryable_codes
        except Exception:
            return False

    def _before_sleep(retry_state: "tenacity.RetryCallState") -> None:  # type: ignore[name-defined]
        try:
            exc = retry_state.outcome.exception()
            code = getattr(exc, "code", None)
            logger.warning(
                "Retrying %s after error %s — attempt %s of %s",
                retry_state.fn.__name__,
                code,
                retry_state.attempt_number,
                max_attempts,
            )
        except Exception:
            logger.warning("Retrying %s — attempt %s of %s", retry_state.fn.__name__, retry_state.attempt_number, max_attempts)

    return tenacity.retry(
        stop=tenacity.stop_after_attempt(max_attempts),
        wait=tenacity.wait_exponential(multiplier=1, min=min_wait_seconds, max=max_wait_seconds),
        retry=tenacity.retry_if_exception(_is_retryable_exception),
        before_sleep=_before_sleep,
        reraise=True,
    )


def _log_simple(logger_obj: logging.Logger | None, code: str, details: str | None = None) -> None:
    if logger_obj is None:
        logger_obj = logging.getLogger(__name__)
    suffix = f" | details={details}" if details else ""
    logger_obj.error("%s%s", code, suffix)


def contract_error(logger_obj: logging.Logger | None = None, details: str | None = None) -> str:
    _log_simple(logger_obj, "contract_error", details)
    return "Contract error: listing not found or already redeemed"


def payment_rejected(logger_obj: logging.Logger | None = None, details: str | None = None) -> str:
    _log_simple(logger_obj, "payment_rejected", details)
    return "Payment was rejected by x402 - please check your wallet balance"


def insufficient_balance(logger_obj: logging.Logger | None = None, details: str | None = None) -> str:
    _log_simple(logger_obj, "insufficient_balance", details)
    return "Payment was rejected by x402 - please check your wallet balance"


def low_reputation(logger_obj: logging.Logger | None = None, details: str | None = None) -> str:
    _log_simple(logger_obj, "low_reputation", details)
    return "Insight was skipped because seller reputation is below threshold"

