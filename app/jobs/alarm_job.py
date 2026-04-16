"""Alarm Job — daily 09:00 TR.

For every unique tender referenced in any user's alarms subcollection, fetch
the latest detail from EKAP (rate-limited) and emit the appropriate
notifications to each subscribed user.
"""
from __future__ import annotations

from app.dedup.grouper import group_alarms_by_tender
from app.ekap.client import EkapClient
from app.ekap.models import TenderDetail
from app.firebase import firestore_repo
from app.firebase.firestore_repo import AlarmDoc
from app.jobs.base import BaseJob
from app.notifications.dispatcher import Dispatcher
from app.notifications.templates import (
    completed_template,
    document_change_template,
    reminder_day_template,
)
from app.state.base import StateStore, TenderSnapshot
from app.utils.dates import is_same_tr_day, tr_today
from app.utils.errors import TenderNotFound
from app.utils.logging import logger
from app.utils.metrics import JobMetrics


# Tender status values that indicate the bid has concluded.
# Source: mobil src/constants/maps.js + ihaleDurumAciklama empirical values.
_COMPLETED_STATUS_IDS = {"4", "5", "10", "15", "20"}
_COMPLETED_KEYWORDS = ("sonuç", "sonuc", "tamamlan", "iptal")


def _is_completed(detail: TenderDetail) -> bool:
    durum_id = str(detail.ihale_durum) if detail.ihale_durum is not None else ""
    if durum_id in _COMPLETED_STATUS_IDS:
        return True
    aciklama = (detail.ihale_durum_aciklama or "").lower()
    return any(kw in aciklama for kw in _COMPLETED_KEYWORDS)


def _detect_events(prev: TenderSnapshot | None, detail: TenderDetail) -> set[str]:
    events: set[str] = set()
    if prev is None:
        # No baseline → only record state; don't emit change events on first sight.
        if _is_completed(detail):
            events.add("completed")
        return events

    prev_doc = prev.dokuman_sayisi
    new_doc = detail.dokuman_sayisi
    if prev_doc is not None and new_doc is not None and new_doc != prev_doc:
        events.add("documentChange")

    prev_was_completed = False
    if prev.ihale_durum:
        prev_was_completed = str(prev.ihale_durum) in _COMPLETED_STATUS_IDS
    if not prev_was_completed and _is_completed(detail):
        events.add("completed")
    return events


def _snapshot_from_detail(detail: TenderDetail) -> TenderSnapshot:
    return TenderSnapshot(
        ihale_tarih_saat=detail.ihale_tarih_saat,
        ihale_durum=str(detail.ihale_durum) if detail.ihale_durum is not None else None,
        dokuman_sayisi=detail.dokuman_sayisi,
    )


class AlarmJob(BaseJob):
    name = "alarm_job"

    def __init__(
        self,
        ekap: EkapClient,
        state: StateStore,
        dispatcher: Dispatcher,
    ) -> None:
        self._ekap = ekap
        self._state = state
        self._dispatcher = dispatcher

    async def _gather_alarms(self, uids: list[str]) -> dict[str, list[AlarmDoc]]:
        out: dict[str, list[AlarmDoc]] = {}
        for uid in uids:
            alarms: list[AlarmDoc] = []
            async for a in firestore_repo.iter_user_alarms(uid):
                alarms.append(a)
            if alarms:
                out[uid] = alarms
        return out

    async def _run(self, metrics: JobMetrics) -> None:
        self._ekap.attach_metrics(metrics)
        self._dispatcher.attach_metrics(metrics)

        users_map = await firestore_repo.list_active_users_with_fcm()
        metrics.users = len(users_map)

        per_user_alarms = await self._gather_alarms(list(users_map.keys()))
        alarms_by_tender = group_alarms_by_tender(per_user_alarms)
        metrics.unique_tenders = len(alarms_by_tender)

        today = tr_today()

        for tender_id, subs in alarms_by_tender.items():
            try:
                prev = await self._state.get_tender_state(tender_id)
                try:
                    detail = await self._ekap.get_tender_detail(tender_id)
                except TenderNotFound:
                    logger.warning("tender not found, skipping: {tid}", tid=tender_id)
                    continue

                events = _detect_events(prev, detail)
                await self._state.set_tender_state(tender_id, _snapshot_from_detail(detail))

                for uid, alarm in subs:
                    token = users_map.get(uid)
                    if not token:
                        continue

                    # reminderDay — always check today, no event diff needed
                    if alarm.reminder_day and is_same_tr_day(detail.ihale_tarih_saat, today):
                        await self._dispatcher.dispatch(
                            uid,
                            token,
                            reminder_day_template(detail),
                            idem_key=f"reminderDay:{tender_id}:{today.isoformat()}",
                        )

                    if alarm.document_change and "documentChange" in events:
                        await self._dispatcher.dispatch(
                            uid,
                            token,
                            document_change_template(detail),
                            idem_key=f"documentChange:{tender_id}:{today.isoformat()}",
                        )

                    if alarm.completed and "completed" in events:
                        if not await self._state.was_completed_notified(uid, tender_id):
                            await self._dispatcher.dispatch(
                                uid,
                                token,
                                completed_template(detail),
                                idem_key=f"completed:{tender_id}:{uid}",
                            )
                            await self._state.mark_completed_notified(uid, tender_id)
                            try:
                                await firestore_repo.mark_alarm_completed(uid, tender_id)
                            except Exception as exc:  # noqa: BLE001
                                logger.warning(
                                    "mark_alarm_completed failed uid={uid} tid={tid}: {err}",
                                    uid=uid,
                                    tid=tender_id,
                                    err=exc,
                                )
            except Exception as exc:  # noqa: BLE001
                metrics.failures += 1
                logger.exception(
                    "alarm processing failed tender={tid}: {err}", tid=tender_id, err=exc
                )
