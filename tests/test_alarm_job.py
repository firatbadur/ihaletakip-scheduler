"""End-to-end alarm job tests with fakeredis + in-memory fakes."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.ekap.models import TenderDetail
from app.firebase.firestore_repo import AlarmDoc
from app.jobs.alarm_job import AlarmJob, _detect_events, _is_completed
from app.notifications.dispatcher import Dispatcher
from app.state.base import TenderSnapshot
from app.state.redis_store import RedisStateStore


def _detail(**overrides: Any) -> TenderDetail:
    base = {
        "id": "101",
        "ikn": "2026/111",
        "ihaleAdi": "Test Yapım",
        "idareAdi": "Test Belediyesi",
        "ihaleDurum": "2",
        "dokumanSayisi": 3,
        "ihaleTarihSaat": "2026-04-16T09:30:00",
    }
    base.update(overrides)
    return TenderDetail.model_validate(base)


def test_is_completed_by_status_id() -> None:
    assert _is_completed(_detail(ihaleDurum="15"))
    assert _is_completed(_detail(ihaleDurum="20"))
    assert not _is_completed(_detail(ihaleDurum="2"))


def test_is_completed_by_keyword() -> None:
    assert _is_completed(_detail(ihaleDurum="3", ihaleDurumAciklama="Sonuçlandı"))
    assert _is_completed(_detail(ihaleDurum="3", ihaleDurumAciklama="iptal edildi"))
    assert _is_completed(_detail(ihaleDurum="3", ihaleDurumAciklama="Tamamlandı"))


def test_detect_events_first_sight_no_diff() -> None:
    events = _detect_events(None, _detail())
    assert events == set()


def test_detect_events_first_sight_completed_state() -> None:
    events = _detect_events(None, _detail(ihaleDurum="15"))
    assert events == {"completed"}


def test_detect_events_document_change() -> None:
    prev = TenderSnapshot(ihale_tarih_saat=None, ihale_durum="2", dokuman_sayisi=3)
    events = _detect_events(prev, _detail(dokumanSayisi=4))
    assert "documentChange" in events


def test_detect_events_transitions_to_completed() -> None:
    prev = TenderSnapshot(ihale_tarih_saat=None, ihale_durum="2", dokuman_sayisi=3)
    events = _detect_events(prev, _detail(ihaleDurum="15"))
    assert "completed" in events


@pytest.mark.asyncio
async def test_alarm_job_runs_reminder_day(
    fake_redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = RedisStateStore(fake_redis)

    users_map = {"u1": "token-u1"}
    alarms_map = {
        "u1": [
            AlarmDoc(
                tender_id="101",
                tender_title="Test Yapım",
                tender_ikn="2026/111",
                institution="Test Belediyesi",
                reminder_day=True,
                document_change=False,
                completed=False,
            )
        ]
    }

    monkeypatch.setattr(
        "app.jobs.alarm_job.firestore_repo.list_active_users_with_fcm",
        AsyncMock(return_value=users_map),
    )
    monkeypatch.setattr(
        "app.jobs.alarm_job.firestore_repo.iter_user_alarms",
        lambda uid: _async_iter(alarms_map.get(uid, [])),
    )
    monkeypatch.setattr(
        "app.jobs.alarm_job.firestore_repo.mark_alarm_completed", AsyncMock()
    )
    # Today = the tender day so reminderDay fires
    from datetime import date

    monkeypatch.setattr(
        "app.jobs.alarm_job.tr_today", lambda: date(2026, 4, 16)
    )
    monkeypatch.setattr(
        "app.jobs.alarm_job.is_same_tr_day", lambda *_args, **_kw: True
    )

    ekap = AsyncMock()
    ekap.attach_metrics = lambda _m: None
    ekap.get_tender_detail = AsyncMock(return_value=_detail())

    dispatcher = Dispatcher(fcm=AsyncMock(), state=state)
    monkeypatch.setattr(
        "app.notifications.dispatcher.firestore_repo.write_notification", AsyncMock()
    )
    monkeypatch.setattr(
        "app.notifications.dispatcher.settings.dry_run", True
    )

    job = AlarmJob(ekap, state, dispatcher)
    metrics = await job.run()

    assert metrics.users == 1
    assert metrics.unique_tenders == 1
    assert metrics.notifications_sent >= 1


async def _async_iter(items):
    for item in items:
        yield item
