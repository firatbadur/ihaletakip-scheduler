"""AsyncIOScheduler wiring for alarm_job and saved_filter_job."""
from __future__ import annotations

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobExecutionEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.jobs.alarm_job import AlarmJob
from app.jobs.interest_job import InterestJob
from app.jobs.saved_filter_job import SavedFilterJob
from app.utils.logging import logger


def _listener(event: JobExecutionEvent) -> None:
    if event.exception:
        logger.error(
            "scheduler job crashed: id={jid} err={err}",
            jid=event.job_id,
            err=event.exception,
        )
    else:
        logger.info("scheduler job finished: id={jid}", jid=event.job_id)


def build_scheduler(
    *,
    alarm_job: AlarmJob,
    saved_filter_job: SavedFilterJob,
    interest_job: InterestJob,
) -> AsyncIOScheduler:
    """Create an AsyncIOScheduler pre-wired with all cron jobs."""
    scheduler = AsyncIOScheduler(
        timezone=settings.timezone,
        job_defaults={
            "max_instances": 1,
            "coalesce": True,
            "misfire_grace_time": 3600,
        },
    )

    scheduler.add_job(
        alarm_job.run,
        trigger=CronTrigger.from_crontab(settings.alarm_cron, timezone=settings.timezone),
        id="alarm_job",
        name="AlarmJob (daily)",
        replace_existing=True,
    )
    scheduler.add_job(
        saved_filter_job.run,
        trigger=CronTrigger.from_crontab(
            settings.saved_filter_cron, timezone=settings.timezone
        ),
        id="saved_filter_job",
        name="SavedFilterJob (daily)",
        replace_existing=True,
    )
    scheduler.add_job(
        interest_job.run,
        trigger=CronTrigger.from_crontab(
            settings.interest_cron, timezone=settings.timezone
        ),
        id="interest_job",
        name="InterestJob (hourly 08-17)",
        replace_existing=True,
    )

    scheduler.add_listener(_listener, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)

    logger.info(
        "scheduler built: alarm='{a}' saved_filter='{s}' interest='{i}' tz={tz}",
        a=settings.alarm_cron,
        s=settings.saved_filter_cron,
        i=settings.interest_cron,
        tz=settings.timezone,
    )
    return scheduler
