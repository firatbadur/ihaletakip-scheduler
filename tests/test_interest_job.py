"""InterestJob tests: exclusion, daily cap, dedup."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.ekap.models import TenderSummary
from app.firebase.firestore_repo import SavedFilterDoc
from app.jobs.interest_job import InterestJob, _merge_filters
from app.notifications.dispatcher import Dispatcher
from app.state.redis_store import RedisStateStore


def test_merge_filters_unions_lists() -> None:
    merged = _merge_filters(
        [
            {"ihaleTuruIdList": [1, 2], "ihaleIlIdList": [34]},
            {"ihaleTuruIdList": [2, 3], "ihaleIlIdList": [35]},
        ]
    )
    assert sorted(merged["ihaleTuruIdList"]) == [1, 2, 3]
    assert sorted(merged["ihaleIlIdList"]) == [34, 35]


def test_merge_filters_keeps_first_search_text() -> None:
    merged = _merge_filters(
        [{"searchText": "yapim"}, {"searchText": "hizmet"}]
    )
    assert merged["searchText"] == "yapim"


def _summary(tid: str, ikn: str, ad: str = "Test") -> TenderSummary:
    return TenderSummary.model_validate(
        {"id": tid, "ikn": ikn, "ihaleAdi": ad, "idareAdi": "Belediye"}
    )


@pytest.mark.asyncio
async def test_interest_sends_one_and_excludes_registered(
    fake_redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = RedisStateStore(fake_redis)

    users = {"u1": "tok-u1"}
    filters_by_user = {
        "u1": [
            SavedFilterDoc(
                filter_id="f1", name="Yapim", filters={"searchText": "yapim"}, alarm=False
            )
        ]
    }

    monkeypatch.setattr(
        "app.jobs.interest_job.firestore_repo.list_active_users_with_fcm",
        AsyncMock(return_value=users),
    )
    monkeypatch.setattr(
        "app.jobs.interest_job.firestore_repo.iter_user_saved_filters",
        lambda uid: _aiter(filters_by_user.get(uid, [])),
    )
    # u1 already has "2026/001" in alarms and "2026/002" in savedTenders
    monkeypatch.setattr(
        "app.jobs.interest_job.firestore_repo.get_user_alarm_ikns",
        AsyncMock(return_value={"2026/001"}),
    )
    monkeypatch.setattr(
        "app.jobs.interest_job.firestore_repo.get_user_saved_tender_ikns",
        AsyncMock(return_value={"2026/002"}),
    )

    ekap = AsyncMock()
    ekap.attach_metrics = lambda _m: None
    # 001 (alarm) + 002 (savedTenders) → skip; 003 → dispatched
    ekap.search_tenders = AsyncMock(
        return_value=[
            _summary("100", "2026/001"),
            _summary("200", "2026/002"),
            _summary("300", "2026/003", "Yeni Yapim"),
            _summary("400", "2026/004", "Baska Yapim"),
        ]
    )

    dispatcher = Dispatcher(fcm=AsyncMock(), state=state)
    write = AsyncMock()
    monkeypatch.setattr(
        "app.notifications.dispatcher.firestore_repo.write_notification", write
    )
    monkeypatch.setattr("app.notifications.dispatcher.settings.dry_run", True)

    job = InterestJob(ekap, state, dispatcher)
    metrics = await job.run()

    # Tam 1 push (birinci uyan aday, 003)
    assert metrics.notifications_sent == 1
    payload = write.call_args.args[1]
    assert payload["tenderIkn"] == "2026/003"
    assert payload["title"] == "İlgilenebileceğiniz İlan"

    # Aynı tetiklemeyi tekrar çalıştırsak bile aynı IKN bildirilmez (dedup)
    ekap.search_tenders.reset_mock()
    # Yeni run: `interest_notified:u1` zaten 003'ü içeriyor → 004'ü seçmeli
    metrics2 = await job.run()
    assert metrics2.notifications_sent == 1
    assert write.call_args.args[1]["tenderIkn"] == "2026/004"


@pytest.mark.asyncio
async def test_interest_respects_daily_cap(
    fake_redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = RedisStateStore(fake_redis)

    users = {"u1": "tok-u1"}
    filters = {"u1": [SavedFilterDoc("f1", "F", {}, False)]}

    monkeypatch.setattr(
        "app.jobs.interest_job.firestore_repo.list_active_users_with_fcm",
        AsyncMock(return_value=users),
    )
    monkeypatch.setattr(
        "app.jobs.interest_job.firestore_repo.iter_user_saved_filters",
        lambda uid: _aiter(filters.get(uid, [])),
    )
    monkeypatch.setattr(
        "app.jobs.interest_job.firestore_repo.get_user_alarm_ikns",
        AsyncMock(return_value=set()),
    )
    monkeypatch.setattr(
        "app.jobs.interest_job.firestore_repo.get_user_saved_tender_ikns",
        AsyncMock(return_value=set()),
    )

    ekap = AsyncMock()
    ekap.attach_metrics = lambda _m: None
    # 10 aday — cap=3 ile sadece 3 push gitmeli (10 run için)
    ekap.search_tenders = AsyncMock(
        return_value=[_summary(str(i), f"2026/{i:03d}") for i in range(100, 110)]
    )

    dispatcher = Dispatcher(fcm=AsyncMock(), state=state)
    monkeypatch.setattr(
        "app.notifications.dispatcher.firestore_repo.write_notification", AsyncMock()
    )
    monkeypatch.setattr("app.notifications.dispatcher.settings.dry_run", True)
    monkeypatch.setattr("app.config.settings.interest_daily_cap", 3)

    job = InterestJob(ekap, state, dispatcher)
    total_sent = 0
    for _ in range(6):  # 6 tetikleme simule et
        m = await job.run()
        total_sent += m.notifications_sent
    assert total_sent == 3


@pytest.mark.asyncio
async def test_interest_skips_user_with_no_filters(
    fake_redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = RedisStateStore(fake_redis)
    monkeypatch.setattr(
        "app.jobs.interest_job.firestore_repo.list_active_users_with_fcm",
        AsyncMock(return_value={"u1": "tok"}),
    )
    monkeypatch.setattr(
        "app.jobs.interest_job.firestore_repo.iter_user_saved_filters",
        lambda uid: _aiter([]),
    )

    ekap = AsyncMock()
    ekap.attach_metrics = lambda _m: None
    ekap.search_tenders = AsyncMock()

    dispatcher = Dispatcher(fcm=AsyncMock(), state=state)
    monkeypatch.setattr(
        "app.notifications.dispatcher.firestore_repo.write_notification", AsyncMock()
    )

    job = InterestJob(ekap, state, dispatcher)
    metrics = await job.run()
    assert metrics.notifications_sent == 0
    ekap.search_tenders.assert_not_called()


async def _aiter(items):
    for i in items:
        yield i
