"""Async token bucket rate limiter — per-host pacing to avoid upstream blocking."""
from __future__ import annotations

import asyncio
import random
import time

from app.config import settings


class AsyncTokenBucket:
    """Fixed-rate token bucket. `rate_per_minute` tokens replenish linearly."""

    def __init__(self, rate_per_minute: int, burst: int | None = None) -> None:
        if rate_per_minute <= 0:
            raise ValueError("rate_per_minute must be > 0")
        self._rate_per_sec = rate_per_minute / 60.0
        self._capacity = float(burst if burst is not None else rate_per_minute)
        self._tokens = self._capacity
        self._updated_at = time.monotonic()
        self._lock = asyncio.Lock()
        self.waits = 0  # Number of times acquire() had to sleep

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._updated_at
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate_per_sec)
        self._updated_at = now

    async def acquire(self, amount: float = 1.0) -> None:
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= amount:
                    self._tokens -= amount
                    return
                deficit = amount - self._tokens
                sleep_for = deficit / self._rate_per_sec
            self.waits += 1
            await asyncio.sleep(sleep_for)


async def jitter_sleep(
    min_ms: int | None = None, max_ms: int | None = None
) -> None:
    """Sleep a random interval to avoid thundering-herd on upstreams."""
    lo = settings.jitter_min_ms if min_ms is None else min_ms
    hi = settings.jitter_max_ms if max_ms is None else max_ms
    if hi <= 0:
        return
    await asyncio.sleep(random.uniform(lo, hi) / 1000.0)
