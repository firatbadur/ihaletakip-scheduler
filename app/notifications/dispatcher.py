"""Dual-write dispatcher: Firestore notification doc + FCM push, idempotent."""
from __future__ import annotations

from typing import Any

from app.config import settings
from app.firebase import firestore_repo
from app.firebase.fcm import FcmSender
from app.state.base import StateStore
from app.utils.errors import FcmTokenInvalid
from app.utils.logging import logger
from app.utils.metrics import JobMetrics


class Dispatcher:
    def __init__(
        self,
        fcm: FcmSender,
        state: StateStore,
        *,
        metrics: JobMetrics | None = None,
    ) -> None:
        self._fcm = fcm
        self._state = state
        self._metrics = metrics

    def attach_metrics(self, metrics: JobMetrics) -> None:
        self._metrics = metrics

    async def dispatch(
        self,
        uid: str,
        token: str,
        payload: dict[str, Any],
        *,
        idem_key: str,
    ) -> None:
        if await self._state.idempotency_exists(idem_key):
            if self._metrics:
                self._metrics.notifications_skipped_idem += 1
            logger.debug("skipping (already notified): key={k}", k=idem_key)
            return

        try:
            await firestore_repo.write_notification(uid, payload)
        except Exception as exc:  # noqa: BLE001
            logger.error("firestore write_notification failed uid={uid}: {err}", uid=uid, err=exc)
            if self._metrics:
                self._metrics.failures += 1
            return

        if settings.dry_run:
            logger.info(
                "dry_run: would FCM send uid={uid} title={title}",
                uid=uid,
                title=payload.get("title"),
            )
        else:
            try:
                await self._fcm.send(token, payload)
            except FcmTokenInvalid as exc:
                logger.warning("fcm token invalid for uid={uid}: {err} — clearing", uid=uid, err=exc)
                try:
                    await firestore_repo.clear_fcm_token(uid)
                except Exception as clear_exc:  # noqa: BLE001
                    logger.error("failed to clear fcm token uid={uid}: {err}", uid=uid, err=clear_exc)
            except Exception as exc:  # noqa: BLE001
                logger.error("fcm send failed uid={uid}: {err}", uid=uid, err=exc)
                if self._metrics:
                    self._metrics.failures += 1
                return

        await self._state.add_idempotency(idem_key, ttl_seconds=7 * 24 * 3600)
        if self._metrics:
            self._metrics.notifications_sent += 1
