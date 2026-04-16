"""Pydantic models for EKAP v2 responses."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TenderSummary(BaseModel):
    """A single tender row returned by GetListByParameters."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str | int | None = None
    ikn: str | None = None
    ihale_adi: str | None = Field(default=None, alias="ihaleAdi")
    idare_adi: str | None = Field(default=None, alias="idareAdi")
    ihale_il_adi: str | None = Field(default=None, alias="ihaleIlAdi")
    ihale_il_id: int | None = Field(default=None, alias="ihaleIlId")
    ihale_tip: str | int | None = Field(default=None, alias="ihaleTip")
    ihale_tip_aciklama: str | None = Field(default=None, alias="ihaleTipAciklama")
    ihale_tarih_saat: str | None = Field(default=None, alias="ihaleTarihSaat")
    ihale_durum: int | str | None = Field(default=None, alias="ihaleDurum")
    ihale_durum_aciklama: str | None = Field(default=None, alias="ihaleDurumAciklama")
    dokuman_sayisi: int | None = Field(default=None, alias="dokumanSayisi")


class TenderDetail(BaseModel):
    """Detailed tender document (subset of fields used by the scheduler)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str | int | None = None
    ikn: str | None = None
    ihale_adi: str | None = Field(default=None, alias="ihaleAdi")
    idare_adi: str | None = Field(default=None, alias="idareAdi")
    ihale_tarih_saat: str | None = Field(default=None, alias="ihaleTarihSaat")
    ihale_durum: int | str | None = Field(default=None, alias="ihaleDurum")
    ihale_durum_aciklama: str | None = Field(default=None, alias="ihaleDurumAciklama")
    dokuman_sayisi: int | None = Field(default=None, alias="dokumanSayisi")

    @classmethod
    def from_api_response(cls, payload: dict) -> "TenderDetail":
        """Accept either a wrapped {'item': {...}} or a flat dict."""
        data = payload.get("item") if isinstance(payload, dict) and "item" in payload else payload
        if not isinstance(data, dict):
            data = {}

        # Many detail fields are also nested inside sub-objects; flatten the ones we need.
        ihale_bilgi = data.get("ihaleBilgi") or {}
        merged = {
            "id": data.get("id"),
            "ikn": data.get("ikn"),
            "ihaleAdi": data.get("ihaleAdi"),
            "idareAdi": data.get("idareAdi") or (data.get("idare") or {}).get("ad"),
            "ihaleTarihSaat": data.get("ihaleTarihSaat") or ihale_bilgi.get("ihaleTarihSaat"),
            "ihaleDurum": data.get("ihaleDurum") or ihale_bilgi.get("ihaleDurum"),
            "ihaleDurumAciklama": data.get("ihaleDurumAciklama")
            or ihale_bilgi.get("ihaleDurumAciklama"),
            "dokumanSayisi": data.get("dokumanSayisi") or ihale_bilgi.get("dokumanSayisi"),
        }
        return cls.model_validate({k: v for k, v in merged.items() if v is not None})
