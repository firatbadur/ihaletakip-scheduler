"""Bir kullaniciyi Firestore'da incele (debug)."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main(uid: str) -> None:
    from app.firebase.admin import get_firestore, init_firebase
    from app.utils.logging import logger, setup_logging

    setup_logging()
    init_firebase()
    db = get_firestore()

    snap = db.collection("users").document(uid).get()
    if not snap.exists:
        logger.error("user does not exist: {u}", u=uid)
        return

    data = snap.to_dict() or {}
    logger.info("uid={u}", u=uid)
    logger.info("  displayName={n}", n=data.get("displayName"))
    logger.info("  isActive={a}", a=data.get("isActive"))
    logger.info("  isBeta={b}", b=data.get("isBeta"))
    has_tok = bool(data.get("fcmToken"))
    logger.info("  has_fcm_token={t}", t=has_tok)
    if has_tok:
        tok = data.get("fcmToken")
        logger.info("  token_prefix={p}...", p=tok[:12])

    alarms_n = len(list(db.collection("users").document(uid).collection("alarms").stream()))
    sf_n = len(list(db.collection("users").document(uid).collection("savedFilters").stream()))
    logger.info("  alarms={a} savedFilters={s}", a=alarms_n, s=sf_n)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("uid")
    asyncio.run(main(p.parse_args().uid))
