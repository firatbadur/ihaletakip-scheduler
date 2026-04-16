"""Loguru-based logging setup with PII redaction and file rotation."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from app.config import settings

_SENSITIVE_KEYS = {"fcmToken", "fcm_token", "token", "email", "private_key", "privateKey"}
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{40,}")  # FCM-ish opaque tokens


def _redact_value(key: str, value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if key.lower() in {k.lower() for k in _SENSITIVE_KEYS}:
        return "***REDACTED***"
    return value


def _redact_record(record: dict[str, Any]) -> None:
    # Loguru record["extra"] is a dict of custom fields
    extra = record.get("extra") or {}
    for k, v in list(extra.items()):
        extra[k] = _redact_value(k, v)

    # Redact obvious emails/opaque tokens from the rendered message
    message = record.get("message", "")
    if message:
        message = _EMAIL_RE.sub("***EMAIL***", message)
        # Avoid over-redacting short hex; only very long opaque strings
        message = _TOKEN_RE.sub(
            lambda m: m.group(0) if len(m.group(0)) < 40 else "***TOKEN***", message
        )
        record["message"] = message


def setup_logging() -> None:
    """Configure loguru sinks: stdout + rotating file, with PII redaction."""
    logger.remove()

    def patcher(record: dict[str, Any]) -> None:
        _redact_record(record)

    logger.configure(patcher=patcher)

    logger.add(
        sys.stdout,
        level=settings.log_level,
        serialize=False,
        backtrace=False,
        diagnose=False,
        enqueue=True,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
    )

    log_dir = Path(settings.log_dir)
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_dir / "app.log",
            level=settings.log_level,
            rotation="100 MB",
            retention=7,
            compression="gz",
            serialize=True,
            enqueue=True,
        )
    except OSError as exc:
        # Fall back silently to stdout-only if the log dir isn't writable
        logger.warning("log_dir not writable ({path}): {err}", path=log_dir, err=exc)


__all__ = ["setup_logging", "logger"]
