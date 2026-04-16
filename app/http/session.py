"""Shared httpx.AsyncClient factory."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx

from app.config import settings


@asynccontextmanager
async def create_http_client() -> AsyncIterator[httpx.AsyncClient]:
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
    timeout = httpx.Timeout(settings.http_timeout_seconds)
    async with httpx.AsyncClient(
        http2=True,
        limits=limits,
        timeout=timeout,
        headers={"User-Agent": "IhaleTakip-Scheduler/1.0"},
    ) as client:
        yield client
