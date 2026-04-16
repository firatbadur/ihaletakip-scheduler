"""Firebase Admin SDK initialization (idempotent)."""
from __future__ import annotations

import threading

import firebase_admin
from firebase_admin import credentials, firestore, messaging

from app.config import settings
from app.utils.logging import logger

_lock = threading.Lock()
_initialized = False


def init_firebase() -> None:
    """Initialize the default Firebase app once."""
    global _initialized
    with _lock:
        if _initialized:
            return
        if firebase_admin._apps:  # another caller already init'd
            _initialized = True
            return
        cred = credentials.Certificate(settings.firebase_credentials_path)
        firebase_admin.initialize_app(cred, {"projectId": settings.firebase_project_id})
        _initialized = True
        logger.info(
            "firebase initialized for project={pid}", pid=settings.firebase_project_id
        )


def get_firestore():  # type: ignore[no-untyped-def]
    init_firebase()
    return firestore.client()


def get_messaging():  # type: ignore[no-untyped-def]
    init_firebase()
    return messaging
