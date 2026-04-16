"""Dedup helpers: minimize the number of outbound EKAP calls."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any


def group_alarms_by_tender(
    per_user_alarms: dict[str, list[Any]],
) -> dict[str, list[tuple[str, Any]]]:
    """Input: {uid: [alarm_doc, ...]} -> Output: {tender_id: [(uid, alarm), ...]}."""
    grouped: dict[str, list[tuple[str, Any]]] = defaultdict(list)
    for uid, alarms in per_user_alarms.items():
        for alarm in alarms:
            tid = str(getattr(alarm, "tender_id", None) or "")
            if not tid:
                continue
            grouped[tid].append((uid, alarm))
    return grouped


def filter_fingerprint(filters: dict[str, Any]) -> str:
    """Stable hash of a saved-filter body, ignoring date-range overrides.

    We normalize by dropping `ilanTarihSaat*` fields since the job injects
    today's date independently — otherwise each day would produce a new group.
    """
    normalized = {
        k: v
        for k, v in filters.items()
        if k
        not in {
            "ilanTarihSaatBaslangic",
            "ilanTarihSaatBitis",
            "ihaleTarihSaatBaslangic",
            "ihaleTarihSaatBitis",
            "paginationSkip",
            "paginationTake",
        }
        and v not in (None, [], "")
    }
    encoded = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
    return hashlib.blake2b(encoded.encode("utf-8"), digest_size=16).hexdigest()


def group_filters_by_fingerprint(
    per_user_filters: dict[str, list[Any]],
) -> dict[str, list[tuple[str, Any]]]:
    """Input: {uid: [filter_doc, ...]} -> Output: {fingerprint: [(uid, filter), ...]}."""
    grouped: dict[str, list[tuple[str, Any]]] = defaultdict(list)
    for uid, filters in per_user_filters.items():
        for f in filters:
            if not getattr(f, "alarm", False):
                continue
            fp = filter_fingerprint(getattr(f, "filters", {}) or {})
            grouped[fp].append((uid, f))
    return grouped
