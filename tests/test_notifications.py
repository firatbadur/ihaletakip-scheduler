"""Template and dispatcher unit tests."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ekap.models import TenderDetail, TenderSummary
from app.notifications.dispatcher import Dispatcher
from app.notifications.templates import (
    completed_template,
    document_change_template,
    reminder_day_template,
    saved_filter_match_template,
)
from app.state.redis_store import RedisStateStore
from app.utils.errors import FcmTokenInvalid
from app.utils.metrics import JobMetrics


def _detail(**overrides: Any) -> TenderDetail:
    base = {
        "id": "555",
        "ikn": "2026/000123",
        "ihaleAdi": "Örnek Yapım İşi",
        "idareAdi": "Örnek Belediyesi",
    }
    base.update(overrides)
    return TenderDetail.model_validate(base)


def test_reminder_day_template_shape() -> None:
    payload = reminder_day_template(_detail())
    assert payload["type"] == "tender"
    assert payload["title"] == "İhale Günü"
    assert "Örnek Yapım İşi" in payload["body"]
    assert payload["tenderId"] == "555"


def test_document_change_template_shape() -> None:
    payload = document_change_template(_detail())
    assert payload["title"] == "Doküman Güncellendi"
    assert "dokümanı güncellendi" in payload["body"]


def test_completed_template_shape() -> None:
    payload = completed_template(_detail())
    assert payload["title"] == "İhale Sonuçlandı"


def test_saved_filter_match_template_uses_filter_name() -> None:
    summary = TenderSummary.model_validate(
        {"id": "42", "ihaleAdi": "Beton İşi", "idareAdi": "Belediye"}
    )
    payload = saved_filter_match_template(summary, filter_name="Beton Aramam")
    assert payload["title"] == "Beton Aramam"
    assert "Beton İşi" in payload["body"]


@pytest.mark.asyncio
async def test_dispatcher_skips_on_idempotency(
    fake_redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = RedisStateStore(fake_redis)
    await store.add_idempotency("dup-key", ttl_seconds=60)

    fcm = SimpleNamespace(send=AsyncMock())
    write = AsyncMock()
    monkeypatch.setattr(
        "app.notifications.dispatcher.firestore_repo.write_notification", write
    )

    dispatcher = Dispatcher(fcm, store)  # type: ignore[arg-type]
    metrics = JobMetrics(name="t")
    dispatcher.attach_metrics(metrics)

    await dispatcher.dispatch(
        "u1", "token-xyz", {"title": "t", "body": "b"}, idem_key="dup-key"
    )

    fcm.send.assert_not_awaited()
    write.assert_not_awaited()
    assert metrics.notifications_skipped_idem == 1
    assert metrics.notifications_sent == 0


@pytest.mark.asyncio
async def test_dispatcher_dry_run_skips_fcm_but_writes_firestore(
    fake_redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = RedisStateStore(fake_redis)
    fcm = SimpleNamespace(send=AsyncMock())
    write = AsyncMock()
    monkeypatch.setattr(
        "app.notifications.dispatcher.firestore_repo.write_notification", write
    )
    monkeypatch.setattr("app.notifications.dispatcher.settings.dry_run", True)

    dispatcher = Dispatcher(fcm, store)  # type: ignore[arg-type]
    metrics = JobMetrics(name="t")
    dispatcher.attach_metrics(metrics)

    await dispatcher.dispatch(
        "u1", "token-xyz", {"title": "t", "body": "b"}, idem_key="fresh-key"
    )

    write.assert_awaited_once()
    fcm.send.assert_not_awaited()
    assert metrics.notifications_sent == 1
    assert await store.idempotency_exists("fresh-key")


@pytest.mark.asyncio
async def test_dispatcher_clears_token_on_invalid(
    fake_redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = RedisStateStore(fake_redis)

    fcm = SimpleNamespace(send=AsyncMock(side_effect=FcmTokenInvalid("dead")))
    write = AsyncMock()
    clear = AsyncMock()
    monkeypatch.setattr(
        "app.notifications.dispatcher.firestore_repo.write_notification", write
    )
    monkeypatch.setattr(
        "app.notifications.dispatcher.firestore_repo.clear_fcm_token", clear
    )
    monkeypatch.setattr("app.notifications.dispatcher.settings.dry_run", False)

    dispatcher = Dispatcher(fcm, store)  # type: ignore[arg-type]
    metrics = JobMetrics(name="t")
    dispatcher.attach_metrics(metrics)

    await dispatcher.dispatch(
        "u1", "token-xyz", {"title": "t", "body": "b"}, idem_key="new-key"
    )

    write.assert_awaited_once()
    clear.assert_awaited_once_with("u1")
    assert await store.idempotency_exists("new-key")
