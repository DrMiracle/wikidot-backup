"""Tests for Wikidot retry behavior."""
import httpx
import pytest
from tenacity import wait_none

from wikidot_backup.config import WIKIDOT_RETRY_ATTEMPTS
from wikidot_backup.wikidot.retry import (
    is_retryable_wikidot_error,
    retry_wikidot_request,
)


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    """Create an HTTPStatusError with a real request and response."""
    request = httpx.Request(
        "GET",
        "https://example.test/",
    )
    response = httpx.Response(
        status_code,
        request=request,
    )

    return httpx.HTTPStatusError(
        f"HTTP {status_code}",
        request=request,
        response=response,
    )


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (408, True),
        (429, True),
        (500, True),
        (502, True),
        (503, True),
        (504, True),
        (400, False),
        (401, False),
        (403, False),
        (404, False),
    ],
)
def test_http_retry_classification(
    status_code: int,
    expected: bool,
) -> None:
    """Only transient HTTP status errors should be retryable."""
    error = _http_status_error(status_code)

    assert is_retryable_wikidot_error(error) is expected


def test_transport_error_is_retryable() -> None:
    """Network transport failures should be retried."""
    error = httpx.ReadTimeout("Timed out.")

    assert is_retryable_wikidot_error(error)


def test_unrelated_error_is_not_retryable() -> None:
    """Programming and data-processing errors must fail immediately."""
    error = ValueError("Invalid data.")

    assert not is_retryable_wikidot_error(error)


def test_retry_succeeds_after_transient_failures() -> None:
    """A request should succeed if a later retry succeeds."""
    attempts = 0

    @retry_wikidot_request
    def operation() -> str:
        nonlocal attempts
        attempts += 1

        if attempts < 3:
            raise httpx.ReadTimeout("Temporary failure.")

        return "success"

    # Retry timing itself is not under test here. Removing waits keeps the test deterministic and fast.
    operation.retry.wait = wait_none()

    result = operation()

    assert result == "success"
    assert attempts == 3


def test_non_retryable_error_is_not_repeated() -> None:
    """A non-transient failure should be raised after one attempt."""
    attempts = 0

    @retry_wikidot_request
    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise ValueError("Invalid data.")

    operation.retry.wait = wait_none()

    with pytest.raises(ValueError, match="Invalid data"):
        operation()

    assert attempts == 1


def test_retry_stops_after_maximum_attempts() -> None:
    """Persistent transient failures should stop after the configured limit."""
    attempts = 0

    @retry_wikidot_request
    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("Still unavailable.")

    operation.retry.wait = wait_none()

    with pytest.raises(httpx.ReadTimeout):
        operation()

    assert attempts == WIKIDOT_RETRY_ATTEMPTS
