"""Shared test fixtures for scheduler unit tests."""
from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio


# Ensure tests never touch real credentials paths.
os.environ.setdefault("FIREBASE_CREDENTIALS_PATH", "/tmp/test-credentials.json")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("DRY_RUN", "true")


@pytest_asyncio.fixture
async def fake_redis() -> AsyncIterator["FakeAsyncRedis"]:  # type: ignore[name-defined]
    fakeredis = pytest.importorskip("fakeredis.aioredis")
    client = fakeredis.FakeRedis(decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()
