"""Minimal in-memory metrics used by jobs for end-of-run summary logs."""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class JobMetrics:
    name: str
    started_at: float = field(default_factory=time.monotonic)
    users: int = 0
    unique_tenders: int = 0
    ekap_requests: int = 0
    rate_waits: int = 0
    retries: int = 0
    notifications_sent: int = 0
    notifications_skipped_idem: int = 0
    failures: int = 0

    def duration_ms(self) -> int:
        return int((time.monotonic() - self.started_at) * 1000)

    def as_dict(self) -> dict[str, int | str]:
        return {
            "job": self.name,
            "users": self.users,
            "unique_tenders": self.unique_tenders,
            "ekap_requests": self.ekap_requests,
            "rate_waits": self.rate_waits,
            "retries": self.retries,
            "notifications_sent": self.notifications_sent,
            "notifications_skipped_idem": self.notifications_skipped_idem,
            "failures": self.failures,
            "duration_ms": self.duration_ms(),
        }
