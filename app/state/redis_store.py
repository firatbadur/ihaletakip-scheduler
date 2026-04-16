"""Redis-backed StateStore implementation."""
from __future__ import annotations

import redis.asyncio as aioredis

from app.config import settings
from app.state.base import StateStore, TenderSnapshot


_DAY_SECONDS = 24 * 60 * 60


class RedisStateStore(StateStore):
    def __init__(self, redis: aioredis.Redis) -> None:
        self._r = redis

    @classmethod
    def from_settings(cls) -> "RedisStateStore":
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        return cls(client)

    async def close(self) -> None:
        await self._r.aclose()

    # --- tender_state -------------------------------------------------------

    async def get_tender_state(self, tender_id: str) -> TenderSnapshot | None:
        data = await self._r.hgetall(f"tender_state:{tender_id}")
        if not data:
            return None
        doc = data.get("dokuman_sayisi")
        return TenderSnapshot(
            ihale_tarih_saat=data.get("ihale_tarih_saat") or None,
            ihale_durum=data.get("ihale_durum") or None,
            dokuman_sayisi=int(doc) if doc and doc.isdigit() else None,
        )

    async def set_tender_state(self, tender_id: str, snapshot: TenderSnapshot) -> None:
        mapping = {
            "ihale_tarih_saat": snapshot.ihale_tarih_saat or "",
            "ihale_durum": snapshot.ihale_durum or "",
            "dokuman_sayisi": str(snapshot.dokuman_sayisi) if snapshot.dokuman_sayisi is not None else "",
        }
        await self._r.hset(f"tender_state:{tender_id}", mapping=mapping)

    # --- notified_tenders ---------------------------------------------------

    async def get_notified_tenders(self, uid: str, filter_id: str) -> set[str]:
        members = await self._r.smembers(f"notified_tenders:{uid}:{filter_id}")
        return set(members or ())

    async def add_notified_tender(self, uid: str, filter_id: str, tender_id: str) -> None:
        key = f"notified_tenders:{uid}:{filter_id}"
        async with self._r.pipeline(transaction=False) as pipe:
            pipe.sadd(key, tender_id)
            pipe.expire(key, 90 * _DAY_SECONDS)
            await pipe.execute()

    # --- alarm completed ----------------------------------------------------

    async def was_completed_notified(self, uid: str, tender_id: str) -> bool:
        return bool(await self._r.exists(f"alarm_completed:{uid}:{tender_id}"))

    async def mark_completed_notified(self, uid: str, tender_id: str) -> None:
        await self._r.set(
            f"alarm_completed:{uid}:{tender_id}", "1", ex=365 * _DAY_SECONDS
        )

    # --- idempotency --------------------------------------------------------

    async def idempotency_exists(self, key: str) -> bool:
        return bool(await self._r.exists(f"idem:{key}"))

    async def add_idempotency(self, key: str, ttl_seconds: int = 7 * _DAY_SECONDS) -> None:
        await self._r.set(f"idem:{key}", "1", ex=ttl_seconds)
