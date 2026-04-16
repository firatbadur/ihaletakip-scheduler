"""RedisStateStore tests against fakeredis."""
from __future__ import annotations

import pytest

from app.state.base import TenderSnapshot
from app.state.redis_store import RedisStateStore


@pytest.mark.asyncio
async def test_tender_state_roundtrip(fake_redis) -> None:
    store = RedisStateStore(fake_redis)
    assert await store.get_tender_state("123") is None

    snap = TenderSnapshot(ihale_tarih_saat="2026-04-20", ihale_durum="2", dokuman_sayisi=3)
    await store.set_tender_state("123", snap)

    got = await store.get_tender_state("123")
    assert got is not None
    assert got.ihale_tarih_saat == "2026-04-20"
    assert got.ihale_durum == "2"
    assert got.dokuman_sayisi == 3


@pytest.mark.asyncio
async def test_notified_tenders_set_semantics(fake_redis) -> None:
    store = RedisStateStore(fake_redis)
    await store.add_notified_tender("u1", "f1", "t1")
    await store.add_notified_tender("u1", "f1", "t2")
    await store.add_notified_tender("u1", "f1", "t1")  # duplicate

    seen = await store.get_notified_tenders("u1", "f1")
    assert seen == {"t1", "t2"}


@pytest.mark.asyncio
async def test_completed_notified_flag(fake_redis) -> None:
    store = RedisStateStore(fake_redis)
    assert await store.was_completed_notified("u1", "t1") is False
    await store.mark_completed_notified("u1", "t1")
    assert await store.was_completed_notified("u1", "t1") is True


@pytest.mark.asyncio
async def test_idempotency_guard(fake_redis) -> None:
    store = RedisStateStore(fake_redis)
    assert await store.idempotency_exists("k1") is False
    await store.add_idempotency("k1", ttl_seconds=60)
    assert await store.idempotency_exists("k1") is True
