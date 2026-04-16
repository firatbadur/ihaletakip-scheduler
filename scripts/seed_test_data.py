"""Test verisi seed eder / temizler.

  python scripts/seed_test_data.py seed <uid>
  python scripts/seed_test_data.py clean <uid>

Seed davranisi:
  - 1 alarm dokumani (bugunun ilk EKAP tender'i, reminderDay=True,
    documentChange=True)
  - 1 savedFilter dokumani (alarm=True, ihaleTuruIdList=[2] -> bugunun yapim
    ihaleleri, bunlar icin push gelir)

Tum seed kayitlari `__scheduler_test__: true` isaretlenir, clean bu isaretli
kayitlari siler.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_MARKER_KEY = "schedulerTest"


async def _fetch_a_tender() -> dict:
    from app.ekap.client import EkapClient
    from app.ekap.crypto import EkapSigner
    from app.http.rate_limiter import AsyncTokenBucket
    from app.http.session import create_http_client
    from app.utils.dates import tr_today

    today = tr_today().strftime("%Y-%m-%d")
    async with create_http_client() as http:
        bucket = AsyncTokenBucket(rate_per_minute=30)
        client = EkapClient(http, bucket, EkapSigner())
        tenders = await client.search_tenders(
            {
                "ilanTarihSaatBaslangic": today,
                "ilanTarihSaatBitis": today,
                "paginationTake": 1,
            }
        )
    if not tenders:
        raise RuntimeError("no tenders returned from EKAP today; cannot seed")
    t = tenders[0]
    return {
        "id": str(t.id),
        "ikn": t.ikn or "",
        "ihaleAdi": t.ihale_adi or "Test",
        "idareAdi": t.idare_adi or "Test",
    }


async def seed(uid: str) -> None:
    from app.firebase.admin import get_firestore, init_firebase
    from app.utils.logging import logger, setup_logging

    setup_logging()
    init_firebase()
    db = get_firestore()

    tender = await _fetch_a_tender()
    logger.info(
        "seeding with tender id={id} ikn={ikn} ad={ad}",
        id=tender["id"],
        ikn=tender["ikn"],
        ad=tender["ihaleAdi"][:50],
    )

    alarm_ref = db.collection("users").document(uid).collection("alarms").document(
        tender["id"]
    )
    alarm_ref.set(
        {
            "tenderId": tender["id"],
            "tenderTitle": tender["ihaleAdi"],
            "tenderIkn": tender["ikn"],
            "institution": tender["idareAdi"],
            "reminderDay": True,
            "documentChange": True,
            "completed": False,
            TEST_MARKER_KEY: True,
        }
    )
    logger.info("alarm seeded at users/{u}/alarms/{t}", u=uid, t=tender["id"])

    filter_ref = db.collection("users").document(uid).collection("savedFilters").document(
        "schedulerSmoke"
    )
    filter_ref.set(
        {
            "name": "Scheduler Smoke Filter",
            "filters": {"ihaleTuruIdList": [2]},  # yapim ihaleleri
            "tags": [],
            "alarm": True,
            TEST_MARKER_KEY: True,
        }
    )
    logger.info("savedFilter seeded at users/{u}/savedFilters/schedulerSmoke", u=uid)

    logger.success("seed done")


async def clean(uid: str) -> None:
    from app.firebase.admin import get_firestore, init_firebase
    from app.utils.logging import logger, setup_logging

    setup_logging()
    init_firebase()
    db = get_firestore()

    removed = 0
    for sub in ("alarms", "savedFilters", "notifications"):
        coll = db.collection("users").document(uid).collection(sub)
        for doc in coll.where(TEST_MARKER_KEY, "==", True).stream():
            doc.reference.delete()
            removed += 1
            logger.info("removed {s}/{i}", s=sub, i=doc.id)

    logger.success("clean done, removed={n}", n=removed)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cmd", choices=("seed", "clean"))
    parser.add_argument("uid")
    args = parser.parse_args()
    fn = seed if args.cmd == "seed" else clean
    asyncio.run(fn(args.uid))


if __name__ == "__main__":
    main()
