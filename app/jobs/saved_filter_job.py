"""SavedFilter Job — daily 10:00 TR.

Groups every user's `alarm=true` saved filters by a normalized fingerprint,
hits EKAP once per group for tenders published today, and dispatches per-user
notifications only for tenders that user hasn't been notified about yet.
"""
from __future__ import annotations

from app.dedup.grouper import group_filters_by_fingerprint
from app.ekap.client import EkapClient
from app.firebase import firestore_repo
from app.firebase.firestore_repo import SavedFilterDoc
from app.jobs.base import BaseJob
from app.notifications.dispatcher import Dispatcher
from app.notifications.templates import saved_filter_match_template
from app.state.base import StateStore
from app.utils.dates import to_ekap_date, tr_today
from app.utils.logging import logger
from app.utils.metrics import JobMetrics


class SavedFilterJob(BaseJob):
    name = "saved_filter_job"

    def __init__(
        self,
        ekap: EkapClient,
        state: StateStore,
        dispatcher: Dispatcher,
    ) -> None:
        self._ekap = ekap
        self._state = state
        self._dispatcher = dispatcher

    async def _gather_saved_filters(
        self, uids: list[str]
    ) -> dict[str, list[SavedFilterDoc]]:
        out: dict[str, list[SavedFilterDoc]] = {}
        for uid in uids:
            filters: list[SavedFilterDoc] = []
            async for f in firestore_repo.iter_user_saved_filters(uid):
                if f.alarm:
                    filters.append(f)
            if filters:
                out[uid] = filters
        return out

    async def _run(self, metrics: JobMetrics) -> None:
        self._ekap.attach_metrics(metrics)
        self._dispatcher.attach_metrics(metrics)

        users_map = await firestore_repo.list_active_users_with_fcm()
        metrics.users = len(users_map)

        per_user_filters = await self._gather_saved_filters(list(users_map.keys()))
        grouped = group_filters_by_fingerprint(per_user_filters)
        metrics.unique_tenders = len(grouped)

        today = tr_today()
        today_str = to_ekap_date(today)

        for fingerprint, members in grouped.items():
            try:
                base_filter = members[0][1].filters
                body = {
                    **base_filter,
                    "ilanTarihSaatBaslangic": today_str,
                    "ilanTarihSaatBitis": today_str,
                    "paginationSkip": 0,
                    "paginationTake": 50,
                }
                tenders = await self._ekap.search_tenders(body)
                if not tenders:
                    continue

                for uid, sf in members:
                    token = users_map.get(uid)
                    if not token:
                        continue
                    seen = await self._state.get_notified_tenders(uid, sf.filter_id)
                    for t in tenders:
                        tid = str(t.id) if t.id is not None else None
                        if not tid or tid in seen:
                            continue
                        await self._dispatcher.dispatch(
                            uid,
                            token,
                            saved_filter_match_template(t, filter_name=sf.name),
                            idem_key=f"savedFilter:{sf.filter_id}:{tid}",
                        )
                        await self._state.add_notified_tender(uid, sf.filter_id, tid)
            except Exception as exc:  # noqa: BLE001
                metrics.failures += 1
                logger.exception(
                    "saved_filter processing failed fp={fp}: {err}", fp=fingerprint, err=exc
                )
