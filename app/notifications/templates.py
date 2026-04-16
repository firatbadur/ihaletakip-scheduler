"""Turkish notification message templates."""
from __future__ import annotations

from typing import Any

from app.ekap.models import TenderDetail, TenderSummary


def _title(text: str, limit: int = 60) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def reminder_day_template(detail: TenderDetail) -> dict[str, Any]:
    name = detail.ihale_adi or "İhale"
    return {
        "type": "tender",
        "title": "İhale Günü",
        "body": f"Bugün ihale günü: {_title(name)}",
        "tenderId": detail.id,
        "tenderTitle": detail.ihale_adi,
        "tenderIkn": detail.ikn,
        "institution": detail.idare_adi,
    }


def document_change_template(detail: TenderDetail) -> dict[str, Any]:
    name = detail.ihale_adi or "İhale"
    return {
        "type": "tender",
        "title": "Doküman Güncellendi",
        "body": f"{_title(name)} dokümanı güncellendi",
        "tenderId": detail.id,
        "tenderTitle": detail.ihale_adi,
        "tenderIkn": detail.ikn,
        "institution": detail.idare_adi,
    }


def completed_template(detail: TenderDetail) -> dict[str, Any]:
    name = detail.ihale_adi or "İhale"
    return {
        "type": "tender",
        "title": "İhale Sonuçlandı",
        "body": f"{_title(name)} ihalesi tamamlandı",
        "tenderId": detail.id,
        "tenderTitle": detail.ihale_adi,
        "tenderIkn": detail.ikn,
        "institution": detail.idare_adi,
    }


def saved_filter_match_template(
    tender: TenderSummary, *, filter_name: str
) -> dict[str, Any]:
    name = tender.ihale_adi or "Yeni ihale"
    return {
        "type": "tender",
        "title": _title(filter_name),
        "body": f"Yeni ihale: {_title(name)}",
        "tenderId": tender.id,
        "tenderTitle": tender.ihale_adi,
        "tenderIkn": tender.ikn,
        "institution": tender.idare_adi,
    }
