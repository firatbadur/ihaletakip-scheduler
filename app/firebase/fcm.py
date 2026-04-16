"""FCM push sender with unregistered-token handling."""
from __future__ import annotations

import asyncio
from typing import Any

from firebase_admin import messaging as fa_messaging

from app.firebase.admin import get_messaging
from app.utils.errors import FcmTokenInvalid
from app.utils.logging import logger


class FcmSender:
    async def send(self, token: str, payload: dict[str, Any]) -> None:
        """Send a single FCM message. Raises FcmTokenInvalid if token is dead."""
        messaging = get_messaging()
        title = payload.get("title", "")
        body = payload.get("body", "")

        # All data fields must be strings (iOS requirement).
        data = {
            k: ("" if v is None else str(v))
            for k, v in {
                "type": payload.get("type", "info"),
                "tenderId": payload.get("tenderId"),
                "tenderTitle": payload.get("tenderTitle"),
                "tenderIkn": payload.get("tenderIkn"),
                "institution": payload.get("institution"),
            }.items()
        }

        android = messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(
                channel_id="ihaletakip",
                sound="default",
            ),
        )
        apns = messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(sound="default", content_available=True),
            ),
        )
        message = messaging.Message(
            token=token,
            notification=messaging.Notification(title=title, body=body),
            data=data,
            android=android,
            apns=apns,
        )

        try:
            message_id = await asyncio.to_thread(messaging.send, message)
            logger.debug("fcm sent id={mid}", mid=message_id)
        except fa_messaging.UnregisteredError as exc:
            raise FcmTokenInvalid("token unregistered") from exc
        except fa_messaging.SenderIdMismatchError as exc:
            raise FcmTokenInvalid("sender id mismatch") from exc
        except (ValueError,) as exc:
            raise FcmTokenInvalid(str(exc)) from exc
