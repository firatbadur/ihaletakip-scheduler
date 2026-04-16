"""Rate limiter unit tests."""
from __future__ import annotations

import asyncio
import time

import pytest

from app.http.rate_limiter import AsyncTokenBucket


@pytest.mark.asyncio
async def test_initial_burst_is_free() -> None:
    bucket = AsyncTokenBucket(rate_per_minute=60, burst=5)
    start = time.monotonic()
    for _ in range(5):
        await bucket.acquire()
    assert time.monotonic() - start < 0.1
    assert bucket.waits == 0


@pytest.mark.asyncio
async def test_waits_when_bucket_empty() -> None:
    # 120/min = 2 tokens/sec; burst=1 so the 2nd acquire waits ~0.5s
    bucket = AsyncTokenBucket(rate_per_minute=120, burst=1)
    await bucket.acquire()
    start = time.monotonic()
    await bucket.acquire()
    elapsed = time.monotonic() - start
    assert 0.3 < elapsed < 0.9
    assert bucket.waits == 1


def test_invalid_rate_rejected() -> None:
    with pytest.raises(ValueError):
        AsyncTokenBucket(rate_per_minute=0)
