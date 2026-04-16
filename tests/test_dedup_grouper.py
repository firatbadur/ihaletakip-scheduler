"""Unit tests for dedup.grouper."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.dedup.grouper import (
    filter_fingerprint,
    group_alarms_by_tender,
    group_filters_by_fingerprint,
)


@dataclass
class FakeAlarm:
    tender_id: str


@dataclass
class FakeFilter:
    filter_id: str
    alarm: bool
    filters: dict[str, Any] = field(default_factory=dict)


def test_group_alarms_by_tender_collapses_duplicates() -> None:
    grouped = group_alarms_by_tender(
        {
            "u1": [FakeAlarm("100"), FakeAlarm("200")],
            "u2": [FakeAlarm("100")],
        }
    )
    assert set(grouped.keys()) == {"100", "200"}
    assert {uid for uid, _ in grouped["100"]} == {"u1", "u2"}
    assert {uid for uid, _ in grouped["200"]} == {"u1"}


def test_group_alarms_skips_empty_ids() -> None:
    grouped = group_alarms_by_tender({"u1": [FakeAlarm("")]})
    assert grouped == {}


def test_filter_fingerprint_ignores_date_and_pagination() -> None:
    f1 = {"searchText": "yapim", "ilanTarihSaatBaslangic": "2026-04-16", "paginationTake": 50}
    f2 = {"searchText": "yapim", "ilanTarihSaatBaslangic": "2026-04-17", "paginationTake": 10}
    assert filter_fingerprint(f1) == filter_fingerprint(f2)


def test_filter_fingerprint_different_search_text_differs() -> None:
    assert filter_fingerprint({"searchText": "a"}) != filter_fingerprint({"searchText": "b"})


def test_group_filters_by_fingerprint_groups_and_skips_alarm_false() -> None:
    grouped = group_filters_by_fingerprint(
        {
            "u1": [
                FakeFilter("f1", alarm=True, filters={"searchText": "yapim"}),
                FakeFilter("f2", alarm=False, filters={"searchText": "yapim"}),
            ],
            "u2": [
                FakeFilter("f3", alarm=True, filters={"searchText": "yapim"}),
            ],
        }
    )
    assert len(grouped) == 1
    fp, members = next(iter(grouped.items()))
    assert {uid for uid, _ in members} == {"u1", "u2"}
    assert all(f.alarm for _, f in members)
