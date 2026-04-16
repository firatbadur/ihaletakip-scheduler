"""BaseJob — shared lifecycle, metrics, and error isolation for scheduler jobs."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.utils.logging import logger
from app.utils.metrics import JobMetrics


class BaseJob(ABC):
    name: str = "base_job"

    @abstractmethod
    async def _run(self, metrics: JobMetrics) -> None:
        """Subclasses implement actual work here."""

    async def run(self) -> JobMetrics:
        metrics = JobMetrics(name=self.name)
        logger.info("job start: {name}", name=self.name)
        try:
            await self._run(metrics)
        except Exception as exc:  # noqa: BLE001
            metrics.failures += 1
            logger.exception("job failed: {name} — {err}", name=self.name, err=exc)
        logger.info("job done: {summary}", summary=metrics.as_dict())
        return metrics
