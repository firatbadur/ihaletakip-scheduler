"""Turkish timezone and date-format helpers for EKAP API."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import settings

TR_TZ = ZoneInfo(settings.timezone)


def tr_now() -> datetime:
    return datetime.now(TR_TZ)


def tr_today() -> date:
    return tr_now().date()


def to_ekap_date(d: date | datetime) -> str:
    """Format: YYYY-MM-DD (EKAP v2 API date format)."""
    if isinstance(d, datetime):
        d = d.date()
    return d.strftime("%Y-%m-%d")


def parse_ekap_datetime(value: str | None) -> datetime | None:
    """Parse EKAP response format 'DD.MM.YYYY HH:MM' or 'DD.MM.YYYY'."""
    if not value:
        return None
    value = value.strip()
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=TR_TZ)
        except ValueError:
            continue
    return None


def is_same_tr_day(dt: datetime | str | None, target: date) -> bool:
    if dt is None:
        return False
    if isinstance(dt, str):
        dt = parse_ekap_datetime(dt)
    if dt is None:
        return False
    return dt.astimezone(TR_TZ).date() == target
