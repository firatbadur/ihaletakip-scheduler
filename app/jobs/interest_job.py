"""InterestJob — every hour 08:00-17:00 TR.

Her kullaniciya, kaydettigi filtrelere gore hala katilima acik, kendisi
tarafindan ne alarm'a ne savedTenders'a eklenmis yeni bir ihaleyi "size
ilgilenebileceginiz ilan" olarak onerir.

Kurallar:
  - Bir user'a tetikleme basina MAX 1 bildirim (kullaniciyi bogma)
  - Bir user'a gun icinde MAX `interest_daily_cap` bildirim (varsayilan: 3)
  - Ayni IKN ayni user'a `interest_dedup_days` gun icinde 2. kez gonderilmez
  - EKAP search: `ihaleDurumIdList=[2, 3]` (katilima acik; mobil ile ayni)
  - "Kayitli" (alarms veya savedTenders) ihaleler haric tutulur
"""
from __future__ import annotations

from typing import Any

from app.config import settings
from app.ekap.client import EkapClient
from app.firebase import firestore_repo
from app.firebase.firestore_repo import SavedFilterDoc
from app.jobs.base import BaseJob
from app.notifications.dispatcher import Dispatcher
from app.notifications.templates import interest_template
from app.state.base import StateStore
from app.utils.dates import tr_today
from app.utils.logging import logger
from app.utils.metrics import JobMetrics

# Mobil main ekraninda "katilima acik" bolgeler bu durum ID'leriyle filtreleniyor
# (bkz. IhaleTakip/src/screens/Main/index.js).
_OPEN_STATUS_IDS = [2, 3]


def _merge_filters(filters: list[dict[str, Any]]) -> dict[str, Any]:
    """Bir kullaniciya ait tum filtreleri tek bir EKAP sorgusuna merge eder.

    Farkli filtreler icin ayri EKAP cagrilari yapmak yerine tum sehir/tur/OKAS
    ID listelerini birlestirip tek arama yapariz — aramanin bir user'a ait
    "size ilgilenebilir" candidate havuzu olarak hizmet etmesi yeterli.
    """
    merged: dict[str, Any] = {}
    list_keys = {
        "yasaKapsami4734List",
        "ihaleTuruIdList",
        "ihaleUsulIdList",
        "ihaleUsulAltIdList",
        "ihaleIlIdList",
        "ihaleIlanTuruIdList",
        "teklifTuruIdList",
        "okasBransKodList",
        "okasBransAdiList",
        "idareKodList",
    }
    for f in filters:
        for k, v in f.items():
            if k in list_keys and isinstance(v, list) and v:
                existing = merged.setdefault(k, [])
                for item in v:
                    if item not in existing:
                        existing.append(item)
    # searchText ayri tutulur — birden fazla varsa ilkini al
    for f in filters:
        txt = f.get("searchText")
        if txt and "searchText" not in merged:
            merged["searchText"] = txt
    return merged


class InterestJob(BaseJob):
    name = "interest_job"

    def __init__(
        self,
        ekap: EkapClient,
        state: StateStore,
        dispatcher: Dispatcher,
    ) -> None:
        self._ekap = ekap
        self._state = state
        self._dispatcher = dispatcher

    async def _run(self, metrics: JobMetrics) -> None:
        self._ekap.attach_metrics(metrics)
        self._dispatcher.attach_metrics(metrics)

        users_map = await firestore_repo.list_active_users_with_fcm()
        metrics.users = len(users_map)
        if not users_map:
            return

        # Per-user saved filters (alarm field icinde filtreleme yok)
        per_user_filters: dict[str, list[SavedFilterDoc]] = {}
        for uid in users_map:
            items: list[SavedFilterDoc] = []
            async for f in firestore_repo.iter_user_saved_filters(uid):
                items.append(f)
            if items:
                per_user_filters[uid] = items

        if not per_user_filters:
            return

        today = tr_today()
        today_str = today.isoformat()
        dedup_ttl = settings.interest_dedup_days * 24 * 60 * 60

        # Fingerprint cache: ayni filtre kombinasyonu birden fazla kullanicida
        # varsa EKAP'i bir kez cagir (butun gruplarda tek search/cluster).
        search_cache: dict[str, Any] = {}

        # Tum fingerprintleri ayni cluster'da takip etmiyoruz — per-user
        # merge yaptigimiz icin cache anahtar olarak "user_merge" hash'i kullanilabilir
        # ama basitlige oncelik verelim: her user icin tek bir merged EKAP cagrisi.
        for uid, filters_list in per_user_filters.items():
            try:
                daily_count = await self._state.get_interest_sent_today(uid, today_str)
                if daily_count >= settings.interest_daily_cap:
                    continue

                token = users_map.get(uid)
                if not token:
                    continue

                # Aday havuzu: tum kullanici filtrelerinin union'u + open status
                merged = _merge_filters([f.filters for f in filters_list])
                body = {
                    **merged,
                    "ihaleDurumIdList": _OPEN_STATUS_IDS,
                    "paginationSkip": 0,
                    "paginationTake": 50,
                }
                cache_key = str(sorted(body.items(), key=lambda x: x[0]))
                if cache_key in search_cache:
                    tenders = search_cache[cache_key]
                else:
                    tenders = await self._ekap.search_tenders(body)
                    search_cache[cache_key] = tenders

                if not tenders:
                    continue

                # Hariç tut: kayıtlı alarm veya savedTenders
                excluded_ikns: set[str] = set()
                excluded_ikns |= await firestore_repo.get_user_alarm_ikns(uid)
                excluded_ikns |= await firestore_repo.get_user_saved_tender_ikns(uid)

                # Ilk uyan candidate'i sec
                chosen = None
                for t in tenders:
                    ikn = t.ikn
                    if not ikn:
                        continue
                    if ikn in excluded_ikns:
                        continue
                    if await self._state.was_interest_notified(uid, ikn):
                        continue
                    chosen = t
                    break

                if chosen is None:
                    continue

                idem = f"interest:{uid}:{chosen.ikn}:{today_str}"
                await self._dispatcher.dispatch(
                    uid,
                    token,
                    interest_template(chosen),
                    idem_key=idem,
                )
                await self._state.mark_interest_notified(uid, chosen.ikn, dedup_ttl)
                await self._state.incr_interest_sent_today(uid, today_str)
            except Exception as exc:  # noqa: BLE001
                metrics.failures += 1
                logger.exception("interest failed uid={uid}: {err}", uid=uid, err=exc)
