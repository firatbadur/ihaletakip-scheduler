"""Data-only FCM push testi.

Notification payload GONDERMEZ. Sadece data gonderir; mobil uygulamanin
notifee.displayNotification kodu bunu alip yerel bildirim gosterir.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main(uid: str, title: str, body: str) -> None:
    from firebase_admin import messaging

    from app.firebase.admin import get_firestore, init_firebase
    from app.utils.logging import logger, setup_logging

    setup_logging()
    init_firebase()
    db = get_firestore()

    user = (db.collection("users").document(uid).get().to_dict() or {})
    token = user.get("fcmToken")
    if not token:
        logger.error("user has no fcmToken: {u}", u=uid)
        return

    logger.info("sending data-only to uid={u} token_prefix={p}", u=uid, p=token[:12])

    data = {
        "type": "tender",
        "title": title,
        "body": body,
        "tenderId": "smoke-" + uuid.uuid4().hex[:8],
        "tenderTitle": title,
        "tenderIkn": "TEST/0001",
        "institution": "IhaleTakip Scheduler",
    }

    msg = messaging.Message(
        token=token,
        data=data,  # only data, no notification
        android=messaging.AndroidConfig(priority="high"),
        apns=messaging.APNSConfig(
            headers={"apns-priority": "10", "apns-push-type": "background"},
            payload=messaging.APNSPayload(
                aps=messaging.Aps(content_available=True),
            ),
        ),
    )

    message_id = await asyncio.to_thread(messaging.send, msg)
    logger.success("sent id={mid}", mid=message_id)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("uid")
    p.add_argument("--title", default="Scheduler Test (data-only)")
    p.add_argument("--body", default="Data-only push - notifee tetiklenmeli")
    args = p.parse_args()
    asyncio.run(main(args.uid, args.title, args.body))
