import json
import sqlite3
import pytest

from backend.utils.error_handler import ErrorHandler, MercatorError, ErrorCode, retry_with_backoff


def test_json_decode_maps_to_gemini_parse_failure():
    exc = json.JSONDecodeError("Expecting value", "doc", 0)
    err = ErrorHandler.handle(exc, {"stage": "parse_test"})
    assert isinstance(err, MercatorError)
    assert err.code == ErrorCode.GEMINI_PARSE_FAILURE
    assert "unexpected" in err.user_message.lower() or err.user_message


def test_sqlite_error_maps_to_database_error():
    exc = sqlite3.OperationalError("disk I/O error")
    err = ErrorHandler.handle(exc, {"stage": "db_test"})
    assert isinstance(err, MercatorError)
    assert err.code == ErrorCode.DATABASE_ERROR


def test_unknown_exception_maps_to_unknown_error():
    exc = ValueError("bad input")
    err = ErrorHandler.handle(exc, {"stage": "unknown_test"})
    assert isinstance(err, MercatorError)
    assert err.code == ErrorCode.UNKNOWN_ERROR


def test_meractor_error_passthrough_preserves_id():
    original = MercatorError(ErrorCode.UNKNOWN_ERROR, context={"a": 1})
    handled = ErrorHandler.handle(original, {"stage": "passthrough"})
    assert handled is original
    assert handled.error_id == original.error_id


def test_retry_with_backoff_retries_on_transient_mercator_error():
    calls = {"n": 0}

    @retry_with_backoff(max_attempts=3, min_wait_seconds=0.01, max_wait_seconds=0.02)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise MercatorError(ErrorCode.IPFS_UPLOAD_FAILED)
        return "ok"

    result = flaky()
    assert result == "ok"
    assert calls["n"] == 3


def test_retry_with_backoff_does_not_retry_on_non_mercator_error():
    calls = {"n": 0}

    @retry_with_backoff(max_attempts=3, min_wait_seconds=0.01, max_wait_seconds=0.02)
    def broken():
        calls["n"] += 1
        raise ValueError("fatal")

    with pytest.raises(ValueError):
        broken()
    assert calls["n"] == 1
