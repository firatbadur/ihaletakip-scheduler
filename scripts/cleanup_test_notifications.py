"""Test sirasinda yazilan notification kayitlarini temizler."""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main() -> None:
    from app.firebase.admin import get_firestore, init_firebase
    from app.utils.logging import logger, setup_logging

    setup_logging()
    init_firebase()
    db = get_firestore()

    targets = [
        "t5Z0fzVZsvYbozpeFxbNNZwTFou2",
        "FNfxzLEsI1heyo7F9gMWiIxxy9U2",
    ]

    total = 0
    for uid in targets:
        coll = db.collection("users").document(uid).collection("notifications")
        for doc in coll.stream():
            data = doc.to_dict() or {}
            tid = str(data.get("tenderId") or "")
            title = str(data.get("title") or "")
            institution = str(data.get("institution") or "")
            # Scheduler tarafindan yazilan test kayitlari
            if (
                tid.startswith("smoke-test-")
                or tid.startswith("smoke-")
                or institution == "IhaleTakip Scheduler"
                or "Scheduler" in title
                or "Debug Test" in title
                or "Data-only" in title
                or "Arka Planda Dene" in title
            ):
                doc.reference.delete()
                total += 1
                logger.info("removed {u}/notifications/{d} (title={t})", u=uid, d=doc.id, t=title[:40])

    logger.success("cleanup done, removed={n}", n=total)


if __name__ == "__main__":
    asyncio.run(main())
