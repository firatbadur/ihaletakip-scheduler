"""Firestore read/write helpers wrapped with asyncio executor.

Firestore Python SDK is synchronous; each call is dispatched to a thread pool
so the asyncio event loop (scheduler + http clients) stays responsive.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator

from firebase_admin import firestore as fa_firestore

from app.config import settings
from app.firebase.admin import get_firestore
from app.utils.logging import logger


@dataclass
class UserRef:
    uid: str
    fcm_token: str


@dataclass
class AlarmDoc:
    tender_id: str
    tender_title: str | None
    tender_ikn: str | None
    institution: str | None
    reminder_day: bool
    document_change: bool
    completed: bool


@dataclass
class SavedFilterDoc:
    filter_id: str
    name: str
    filters: dict[str, Any]
    alarm: bool


async def _run(func, *args, **kwargs):  # type: ignore[no-untyped-def]
    return await asyncio.to_thread(func, *args, **kwargs)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def _fetch_active_users_sync() -> list[UserRef]:
    db = get_firestore()
    out: list[UserRef] = []
    query = db.collection("users")
    if settings.only_beta_users:
        query = query.where("isBeta", "==", True)
    for doc in query.stream():
        data = doc.to_dict() or {}
        if data.get("isActive") is False:
            continue
        token = data.get("fcmToken")
        if not token:
            continue
        out.append(UserRef(uid=doc.id, fcm_token=token))
    return out


async def list_active_users_with_fcm() -> dict[str, str]:
    users = await _run(_fetch_active_users_sync)
    logger.info("loaded {n} active users with fcm token", n=len(users))
    return {u.uid: u.fcm_token for u in users}


def _clear_fcm_token_sync(uid: str) -> None:
    db = get_firestore()
    db.collection("users").document(uid).set(
        {"fcmToken": None, "tokenUpdatedAt": fa_firestore.SERVER_TIMESTAMP},
        merge=True,
    )


async def clear_fcm_token(uid: str) -> None:
    await _run(_clear_fcm_token_sync, uid)


# ---------------------------------------------------------------------------
# Alarms
# ---------------------------------------------------------------------------

def _fetch_alarms_sync(uid: str) -> list[AlarmDoc]:
    db = get_firestore()
    out: list[AlarmDoc] = []
    for doc in db.collection("users").document(uid).collection("alarms").stream():
        d = doc.to_dict() or {}
        out.append(
            AlarmDoc(
                tender_id=str(d.get("tenderId") or doc.id),
                tender_title=d.get("tenderTitle"),
                tender_ikn=d.get("tenderIkn"),
                institution=d.get("institution"),
                reminder_day=bool(d.get("reminderDay")),
                document_change=bool(d.get("documentChange")),
                completed=bool(d.get("completed")),
            )
        )
    return out


async def iter_user_alarms(uid: str) -> AsyncIterator[AlarmDoc]:
    alarms = await _run(_fetch_alarms_sync, uid)
    for a in alarms:
        yield a


def _mark_alarm_completed_sync(uid: str, tender_id: str) -> None:
    db = get_firestore()
    ref = db.collection("users").document(uid).collection("alarms").document(str(tender_id))
    ref.set(
        {"completed": True, "updatedAt": fa_firestore.SERVER_TIMESTAMP},
        merge=True,
    )


async def mark_alarm_completed(uid: str, tender_id: str) -> None:
    await _run(_mark_alarm_completed_sync, uid, tender_id)


# ---------------------------------------------------------------------------
# Saved filters
# ---------------------------------------------------------------------------

def _fetch_saved_filters_sync(uid: str) -> list[SavedFilterDoc]:
    db = get_firestore()
    out: list[SavedFilterDoc] = []
    for doc in db.collection("users").document(uid).collection("savedFilters").stream():
        d = doc.to_dict() or {}
        filters = d.get("filters") or {}
        if not isinstance(filters, dict):
            continue
        out.append(
            SavedFilterDoc(
                filter_id=doc.id,
                name=str(d.get("name") or "Kayıtlı filtre"),
                filters=filters,
                alarm=bool(d.get("alarm", False)),
            )
        )
    return out


async def iter_user_saved_filters(uid: str) -> AsyncIterator[SavedFilterDoc]:
    filters = await _run(_fetch_saved_filters_sync, uid)
    for f in filters:
        yield f


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def _write_notification_sync(uid: str, payload: dict[str, Any]) -> None:
    db = get_firestore()
    doc = {
        "type": payload.get("type", "info"),
        "title": payload.get("title", ""),
        "body": payload.get("body", ""),
        "tenderId": payload.get("tenderId"),
        "tenderTitle": payload.get("tenderTitle"),
        "tenderIkn": payload.get("tenderIkn"),
        "institution": payload.get("institution"),
        "read": False,
        "createdAt": fa_firestore.SERVER_TIMESTAMP,
    }
    db.collection("users").document(uid).collection("notifications").add(doc)


async def write_notification(uid: str, payload: dict[str, Any]) -> None:
    await _run(_write_notification_sync, uid, payload)
