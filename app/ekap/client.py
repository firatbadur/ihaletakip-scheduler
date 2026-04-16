"""Async EKAP v2 client with rate limiting, jitter, retry and request signing."""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.config import settings
from app.ekap.crypto import EkapSigner
from app.ekap.models import TenderDetail, TenderSummary
from app.http.rate_limiter import AsyncTokenBucket, jitter_sleep
from app.http.retry import ekap_retry
from app.utils.errors import EkapError, TenderNotFound
from app.utils.logging import logger
from app.utils.metrics import JobMetrics

# EKAP v2 endpoint paths (under ekap_base_url)
_SEARCH_PATH = "/b_ihalearama/api/Ihale/GetListByParameters"
_DETAIL_PATH = "/b_ihalearama/api/IhaleDetay/GetByIhaleIdIhaleDetay"

# Kept in sync with mobil src/api/v1/api.js DEFAULT_SEARCH_BODY
DEFAULT_SEARCH_BODY: dict[str, Any] = {
    "searchText": "",
    "filterType": None,
    "ikNdeAra": True,
    "ihaleAdindaAra": True,
    "searchType": "GirdigimGibi",
    "iknYili": None,
    "iknSayi": None,
    "ihaleTarihSaatBaslangic": None,
    "ihaleTarihSaatBitis": None,
    "ilanTarihSaatBaslangic": None,
    "ilanTarihSaatBitis": None,
    "yasaKapsami4734List": [],
    "ihaleTuruIdList": [],
    "ihaleUsulIdList": [],
    "ihaleUsulAltIdList": [],
    "ihaleIlIdList": [],
    "ihaleDurumIdList": [],
    "ihaleIlanTuruIdList": [],
    "teklifTuruIdList": [],
    "asiriDusukTeklifIdList": [],
    "istisnaMaddeIdList": [],
    "okasBransKodList": [],
    "okasBransAdiList": [],
    "titubbKodList": [],
    "gmdnKodList": [],
    "idareKodList": [],
    "eIhale": None,
    "eEksiltmeYapilacakMi": None,
    "ortakAlimMi": None,
    "kismiTeklifMi": None,
    "fiyatDisiUnsurVarmi": None,
    "ekonomikVeMaliYeterlilikBelgeleriIsteniyorMu": None,
    "meslekiTeknikYeterlilikBelgeleriIsteniyorMu": None,
    "isDeneyimiGosterenBelgelerIsteniyorMu": None,
    "yerliIstekliyeFiyatAvantajiUgulaniyorMu": None,
    "yabanciIsteklilereIzinVeriliyorMu": None,
    "alternatifTeklifVerilebilirMi": None,
    "konsorsiyumKatilabilirMi": None,
    "altYukleniciCalistirilabilirMi": None,
    "fiyatFarkiVerilecekMi": None,
    "avansVerilecekMi": None,
    "cerceveAnlasmaMi": None,
    "personelCalistirilmasinaDayaliMi": None,
    "orderBy": "ihaleTarihi",
    "siralamaTipi": "asc",
    "paginationSkip": 0,
    "paginationTake": 10,
}


class EkapClient:
    """Rate-limited + retrying client for EKAP v2 JSON endpoints."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        rate_limiter: AsyncTokenBucket,
        signer: EkapSigner,
        *,
        concurrency: int | None = None,
        base_url: str | None = None,
        metrics: JobMetrics | None = None,
    ) -> None:
        self._http = http
        self._rate = rate_limiter
        self._signer = signer
        self._sem = asyncio.Semaphore(concurrency or settings.ekap_concurrency)
        self._base = (base_url or settings.ekap_base_url).rstrip("/")
        self._metrics = metrics

    def attach_metrics(self, metrics: JobMetrics) -> None:
        self._metrics = metrics

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base}{path}"
        async for attempt in ekap_retry():
            with attempt:
                await self._rate.acquire()
                async with self._sem:
                    await jitter_sleep()
                    headers = {
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        **self._signer.headers(),
                    }
                    if self._metrics:
                        self._metrics.ekap_requests += 1
                    resp = await self._http.post(url, headers=headers, json=body)
                    if resp.status_code in (429, 500, 502, 503, 504):
                        if self._metrics:
                            self._metrics.retries += 1
                        retry_after = resp.headers.get("Retry-After")
                        if retry_after and retry_after.isdigit():
                            await asyncio.sleep(min(int(retry_after), 60))
                        resp.raise_for_status()
                    resp.raise_for_status()
                    try:
                        return resp.json()
                    except ValueError as exc:
                        raise EkapError(f"invalid JSON from EKAP {path}: {exc}") from exc
        raise EkapError(f"exhausted retries for EKAP {path}")

    async def search_tenders(self, filters: dict[str, Any]) -> list[TenderSummary]:
        body = {**DEFAULT_SEARCH_BODY, **(filters or {})}
        data = await self._post(_SEARCH_PATH, body)
        raw_list = data.get("list") if isinstance(data, dict) else None
        if not isinstance(raw_list, list):
            return []
        out: list[TenderSummary] = []
        for item in raw_list:
            if isinstance(item, dict):
                try:
                    out.append(TenderSummary.model_validate(item))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("failed to parse tender summary: {err}", err=exc)
        return out

    async def get_tender_detail(self, ihale_id: str | int) -> TenderDetail:
        body = {"ihaleId": str(ihale_id)}
        try:
            data = await self._post(_DETAIL_PATH, body)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (400, 404):
                raise TenderNotFound(str(ihale_id)) from exc
            raise
        if not data:
            raise TenderNotFound(str(ihale_id))
        return TenderDetail.from_api_response(data)
