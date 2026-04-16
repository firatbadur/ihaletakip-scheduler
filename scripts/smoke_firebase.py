"""Firebase okuma smoke testi: service account + kullanici/alarm/filter verisi."""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main() -> None:
    from app.firebase import firestore_repo
    from app.firebase.admin import init_firebase
    from app.utils.logging import logger, setup_logging

    setup_logging()
    init_firebase()
    logger.info("Firebase init OK")

    users = await firestore_repo.list_active_users_with_fcm()
    logger.info("active users with fcmToken: {n}", n=len(users))
    for uid, token in list(users.items())[:5]:
        logger.info("  uid={u} token_prefix={tp}", u=uid, tp=(token[:12] if token else "-"))

    if not users:
        logger.warning("no active users with fcmToken; nothing to process")
        return

    sample_uid = next(iter(users))
    logger.info("inspecting uid={u}", u=sample_uid)

    alarms_count = 0
    async for alarm in firestore_repo.iter_user_alarms(sample_uid):
        alarms_count += 1
        if alarms_count <= 3:
            logger.info(
                "  alarm: tender_id={t} title={n} rd={rd} dc={dc} done={c}",
                t=alarm.tender_id,
                n=(alarm.tender_title or "")[:40],
                rd=alarm.reminder_day,
                dc=alarm.document_change,
                c=alarm.completed,
            )
    logger.info("alarms total for {u}: {n}", u=sample_uid, n=alarms_count)

    filters_count = 0
    alarm_true_count = 0
    async for f in firestore_repo.iter_user_saved_filters(sample_uid):
        filters_count += 1
        if f.alarm:
            alarm_true_count += 1
        if filters_count <= 3:
            logger.info(
                "  filter: id={i} name={n} alarm={a} filters_keys={k}",
                i=f.filter_id,
                n=(f.name or "")[:30],
                a=f.alarm,
                k=list((f.filters or {}).keys())[:6],
            )
    logger.info(
        "savedFilters for {u}: total={t} with_alarm={a}",
        u=sample_uid,
        t=filters_count,
        a=alarm_true_count,
    )

    logger.success("Firebase smoke test PASSED")


if __name__ == "__main__":
    asyncio.run(main())
