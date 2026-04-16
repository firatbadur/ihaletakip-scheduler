"""Tenacity retry decorators for EKAP calls (429/5xx exponential backoff)."""
from __future__ import annotations

import httpx
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.utils.logging import logger

_RETRY_STATUS = {429, 500, 502, 503, 504}


def _is_retryable_http_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRY_STATUS
    return isinstance(exc, (httpx.TransportError, httpx.TimeoutException))


def _log_attempt(retry_state: RetryCallState) -> None:
    if retry_state.attempt_number > 1:
        logger.warning(
            "retrying (attempt={attempt}) after {err}",
            attempt=retry_state.attempt_number,
            err=retry_state.outcome.exception() if retry_state.outcome else None,
        )


def ekap_retry() -> AsyncRetrying:
    """Reusable AsyncRetrying instance for EKAP requests."""
    return AsyncRetrying(
        reraise=True,
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception(_is_retryable_http_error),
        before_sleep=_log_attempt,
    )
