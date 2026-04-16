"""Service entrypoint: initialize Firebase, wire jobs, run AsyncIOScheduler forever."""
from __future__ import annotations

import asyncio
import signal
from contextlib import AsyncExitStack

try:
    import uvloop  # type: ignore
except ImportError:  # pragma: no cover - Linux-only dep
    uvloop = None

from app.config import settings
from app.ekap.client import EkapClient
from app.ekap.crypto import EkapSigner
from app.firebase.admin import init_firebase
from app.firebase.fcm import FcmSender
from app.http.rate_limiter import AsyncTokenBucket
from app.http.session import create_http_client
from app.jobs.alarm_job import AlarmJob
from app.jobs.saved_filter_job import SavedFilterJob
from app.notifications.dispatcher import Dispatcher
from app.scheduler.scheduler import build_scheduler
from app.state.redis_store import RedisStateStore
from app.utils.logging import logger, setup_logging


async def _run() -> None:
    setup_logging()
    logger.info(
        "ihaletakip-scheduler starting (dry_run={dr}, only_beta={ob})",
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

        alarm_job = AlarmJob(ekap, state, dispatcher)
        saved_filter_job = SavedFilterJob(ekap, state, dispatcher)

        scheduler = build_scheduler(
            alarm_job=alarm_job,
            saved_filter_job=saved_filter_job,
        )
        scheduler.start()
        logger.info("scheduler started; waiting for triggers...")

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        def _request_stop(sig: signal.Signals) -> None:
            logger.info("signal received: {s} — shutting down", s=sig.name)
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _request_stop, sig)
            except NotImplementedError:  # pragma: no cover - Windows
                signal.signal(sig, lambda *_: stop_event.set())

        try:
            await stop_event.wait()
        finally:
            logger.info("stopping scheduler (wait for running jobs)...")
            scheduler.shutdown(wait=True)

    logger.info("ihaletakip-scheduler stopped cleanly")


def main() -> None:
    if uvloop is not None:
        uvloop.install()
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
