"""Retry policy for transient Wikidot communication failures."""
from __future__ import annotations

from collections.abc import Callable
from typing import ParamSpec, TypeVar

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from wikidot_backup.config import (
    WIKIDOT_RETRY_ATTEMPTS,
    WIKIDOT_RETRY_INITIAL_WAIT_SECONDS,
    WIKIDOT_RETRY_MAX_WAIT_SECONDS,
)


P = ParamSpec("P")
R = TypeVar("R")


def is_retryable_wikidot_error(exception: BaseException) -> bool:
    """Return whether an exception represents a transient Wikidot failure.

    Network and transport failures are considered transient. HTTP responses
    are retried only for request throttling/timeouts or server-side failures.

    Programming errors, validation failures and ordinary client-side HTTP
    errors are intentionally not retried.
    """
    if isinstance(exception, httpx.TransportError):
        return True

    if isinstance(exception, httpx.HTTPStatusError):
        status_code = exception.response.status_code

        return (
            status_code in {408, 429}
            or 500 <= status_code < 600
        )

    return False


def retry_wikidot_request(
    function: Callable[P, R],
) -> Callable[P, R]:
    """Apply the standard retry policy to a Wikidot integration call."""
    return retry(
        retry=retry_if_exception(is_retryable_wikidot_error),
        stop=stop_after_attempt(WIKIDOT_RETRY_ATTEMPTS),
        wait=wait_exponential_jitter(
            initial=WIKIDOT_RETRY_INITIAL_WAIT_SECONDS,
            max=WIKIDOT_RETRY_MAX_WAIT_SECONDS,
        ),
        reraise=True,
    )(function)
