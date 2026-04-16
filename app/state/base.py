"""State store protocol — abstracts Redis / alternative backends."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class TenderSnapshot:
    ihale_tarih_saat: str | None
    ihale_durum: str | None
    dokuman_sayisi: int | None


class StateStore(Protocol):
    async def get_tender_state(self, tender_id: str) -> TenderSnapshot | None: ...

    async def set_tender_state(self, tender_id: str, snapshot: TenderSnapshot) -> None: ...

    async def get_notified_tenders(self, uid: str, filter_id: str) -> set[str]: ...

    async def add_notified_tender(self, uid: str, filter_id: str, tender_id: str) -> None: ...

    async def was_completed_notified(self, uid: str, tender_id: str) -> bool: ...

    async def mark_completed_notified(self, uid: str, tender_id: str) -> None: ...

    async def idempotency_exists(self, key: str) -> bool: ...

    async def add_idempotency(self, key: str, ttl_seconds: int) -> None: ...

    async def close(self) -> None: ...
