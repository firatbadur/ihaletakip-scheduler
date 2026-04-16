"""Belirli bir kullaniciya test push bildirimi gonderir.

Kullanim:
    python scripts/send_push.py <uid> [--title T] [--body B] [--dry-run]

Dispatcher akisini kullanir: Firestore notifications yazar + FCM push gonderir.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from contextlib import AsyncExitStack

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main(uid: str, title: str, body: str, dry_run: bool) -> None:
    from app.firebase.admin import get_firestore, init_firebase
    from app.firebase.fcm import FcmSender
    from app.notifications.dispatcher import Dispatcher
    from app.state.redis_store import RedisStateStore
    from app.utils.logging import logger, setup_logging

    setup_logging()
    init_firebase()
    db = get_firestore()

    snap = db.collection("users").document(uid).get()
    if not snap.exists:
        logger.error("user not found: {u}", u=uid)
        return
    user = snap.to_dict() or {}
    token = user.get("fcmToken")
    if not token:
        logger.error("user has no fcmToken: {u}", u=uid)
        return

    logger.info(
        "target uid={u} isActive={a} token_prefix={p}",
        u=uid,
        a=user.get("isActive"),
        p=token[:12],
    )

    async with AsyncExitStack() as stack:
        state = RedisStateStore.from_settings()
        stack.push_async_callback(state.close)

        dispatcher = Dispatcher(FcmSender(), state)

        if dry_run:
            os.environ["DRY_RUN"] = "true"
            from app.config import settings
            settings.dry_run = True
            logger.info("DRY_RUN: FCM skipped, Firestore write only")

        payload = {
            "type": "tender",
            "title": title,
            "body": body,
            "tenderId": "smoke-test-" + uuid.uuid4().hex[:8],
            "tenderTitle": "Scheduler Smoke Test",
            "tenderIkn": "TEST/0001",
            "institution": "IhaleTakip Scheduler",
        }
        idem = f"smoke-push-{uid}-{uuid.uuid4().hex[:8]}"

        await dispatcher.dispatch(uid, token, payload, idem_key=idem)
        logger.success("dispatch done; check Firestore users/{u}/notifications + device", u=uid)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("uid")
    p.add_argument("--title", default="IhaleTakip Test Bildirim")
    p.add_argument(
        "--body",
        default="Scheduler servisi calisiyor - bu bir test bildirimidir.",
    )
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    asyncio.run(main(args.uid, args.title, args.body, args.dry_run))
