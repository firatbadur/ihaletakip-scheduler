"""End-to-end saved_filter job tests with fakeredis + in-memory fakes."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.ekap.models import TenderSummary
from app.firebase.firestore_repo import SavedFilterDoc
from app.jobs.saved_filter_job import SavedFilterJob
from app.notifications.dispatcher import Dispatcher
from app.state.redis_store import RedisStateStore


@pytest.mark.asyncio
async def test_saved_filter_job_dispatches_new_tenders(
    fake_redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = RedisStateStore(fake_redis)

    users_map = {"u1": "token-u1", "u2": "token-u2"}
    filters_by_user = {
        "u1": [
            SavedFilterDoc(
                filter_id="f1",
                name="Yapım İzmir",
                filters={"searchText": "yapim", "ihaleIlIdList": [35]},
                alarm=True,
            )
        ],
        "u2": [
            SavedFilterDoc(
                filter_id="f2",
                name="Yapım İzmir 2",
                filters={"searchText": "yapim", "ihaleIlIdList": [35]},
                alarm=True,
            )
        ],
    }

    monkeypatch.setattr(
        "app.jobs.saved_filter_job.firestore_repo.list_active_users_with_fcm",
        AsyncMock(return_value=users_map),
    )
    monkeypatch.setattr(
        "app.jobs.saved_filter_job.firestore_repo.iter_user_saved_filters",
        lambda uid: _async_iter(filters_by_user.get(uid, [])),
    )

    tenders = [
        TenderSummary.model_validate(
            {"id": "1001", "ihaleAdi": "Okul Binası", "idareAdi": "Belediye"}
        ),
        TenderSummary.model_validate(
            {"id": "1002", "ihaleAdi": "Yol Yapım", "idareAdi": "Belediye"}
        ),
    ]

    ekap = AsyncMock()
    ekap.attach_metrics = lambda _m: None
    ekap.search_tenders = AsyncMock(return_value=tenders)

    dispatcher = Dispatcher(fcm=AsyncMock(), state=state)
    monkeypatch.setattr(
        "app.notifications.dispatcher.firestore_repo.write_notification", AsyncMock()
    )
    monkeypatch.setattr("app.notifications.dispatcher.settings.dry_run", True)

    job = SavedFilterJob(ekap, state, dispatcher)
    metrics = await job.run()

    # Both u1 and u2 share a fingerprint → a single EKAP call
    ekap.search_tenders.assert_awaited_once()
    assert metrics.unique_tenders == 1
    # 2 users × 2 tenders = 4 notifications on first run
    assert metrics.notifications_sent == 4

    # Second run should emit zero — state now records everyone as notified
    ekap.search_tenders.reset_mock()
    metrics2 = await job.run()
    assert metrics2.notifications_sent == 0


async def _async_iter(items):
    for item in items:
        yield item
