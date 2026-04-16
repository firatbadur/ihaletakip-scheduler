"""Manually trigger a single job execution.

Usage:
    python scripts/run_once.py alarm [--dry-run] [--only-beta]
    python scripts/run_once.py saved_filter [--dry-run] [--only-beta]
    python scripts/run_once.py interest [--dry-run] [--only-beta]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from contextlib import AsyncExitStack

# Allow running from project root without installing the package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def _main(job_name: str) -> None:
    # Settings re-read happens at import time; exports must be set before import.
    from app.ekap.client import EkapClient
    from app.ekap.crypto import EkapSigner
    from app.firebase.admin import init_firebase
    from app.firebase.fcm import FcmSender
    from app.http.rate_limiter import AsyncTokenBucket
    from app.http.session import create_http_client
    from app.jobs.alarm_job import AlarmJob
    from app.jobs.interest_job import InterestJob
    from app.jobs.saved_filter_job import SavedFilterJob
    from app.notifications.dispatcher import Dispatcher
    from app.state.redis_store import RedisStateStore
    from app.utils.logging import logger, setup_logging
    from app.config import settings

    setup_logging()
    logger.info(
        "run_once: job={j} dry_run={dr} only_beta={ob}",
        j=job_name,
        dr=settings.dry_run,
        ob=settings.only_beta_users,
    )
    init_firebase()

    async with AsyncExitStack() as stack:
        http = await stack.enter_async_context(create_http_client())
        state = RedisStateStore.from_settings()
        stack.push_async_callback(state.close)

        signer = EkapSigner()
        rate_limiter = AsyncTokenBucket(settings.ekap_rate_per_min)
        ekap = EkapClient(http, rate_limiter, signer)
        fcm = FcmSender()
        dispatcher = Dispatcher(fcm, state)

        if job_name == "alarm":
            metrics = await AlarmJob(ekap, state, dispatcher).run()
        elif job_name == "saved_filter":
            metrics = await SavedFilterJob(ekap, state, dispatcher).run()
        elif job_name == "interest":
            metrics = await InterestJob(ekap, state, dispatcher).run()
        else:  # pragma: no cover - argparse prevents this
            raise ValueError(f"unknown job: {job_name}")

        logger.info("run_once done: {m}", m=metrics.as_dict())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IhaleTakip scheduler: one-shot runner")
    parser.add_argument("job", choices=("alarm", "saved_filter", "interest"))
    parser.add_argument("--dry-run", action="store_true", help="skip FCM send (Firestore writes still occur)")
    parser.add_argument("--only-beta", action="store_true", help="limit to users with isBeta=true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.dry_run:
        os.environ["DRY_RUN"] = "true"
    if args.only_beta:
        os.environ["ONLY_BETA_USERS"] = "true"
    asyncio.run(_main(args.job))


if __name__ == "__main__":
    main()
