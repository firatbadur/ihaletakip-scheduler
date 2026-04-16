"""EKAP v2 request signing — AES-192-CBC + PKCS7, mobil crypto-js parity.

Mobil kaynak: src/api/v1/calls.js

Headers produced:
  api-version: v1
  X-Custom-Request-Guid: <uuid4>
  X-Custom-Request-R8id: base64(AES192-CBC(guid, key, iv))
  X-Custom-Request-Siv: base64(iv)
  X-Custom-Request-Ts: base64(AES192-CBC(timestamp_ms_string, key, iv))
"""
from __future__ import annotations

import base64
import os
import time
import uuid
from dataclasses import dataclass

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.config import settings


def _encrypt_aes192_cbc(plaintext: str, key: bytes, iv: bytes) -> bytes:
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    return encryptor.update(padded) + encryptor.finalize()


@dataclass(frozen=True)
class SigningHeaders:
    api_version: str
    guid: str
    r8id: str
    siv: str
    ts: str

    def as_dict(self) -> dict[str, str]:
        return {
            "api-version": self.api_version,
            "X-Custom-Request-Guid": self.guid,
            "X-Custom-Request-R8id": self.r8id,
            "X-Custom-Request-Siv": self.siv,
            "X-Custom-Request-Ts": self.ts,
        }


class EkapSigner:
    """Generates custom request headers expected by EKAP v2 endpoints."""

    def __init__(self, signing_key: str | None = None) -> None:
        key_str = signing_key or settings.ekap_signing_key
        key_bytes = key_str.encode("utf-8")
        if len(key_bytes) != 24:
            raise ValueError(
                f"EKAP signing key must be 24 bytes (AES-192); got {len(key_bytes)}"
            )
        self._key = key_bytes

    def sign(
        self,
        *,
        guid: str | None = None,
        iv: bytes | None = None,
        timestamp_ms: int | None = None,
    ) -> SigningHeaders:
        _guid = guid or str(uuid.uuid4())
        _iv = iv or os.urandom(16)
        _ts = str(timestamp_ms if timestamp_ms is not None else int(time.time() * 1000))

        r8id_ct = _encrypt_aes192_cbc(_guid, self._key, _iv)
        ts_ct = _encrypt_aes192_cbc(_ts, self._key, _iv)

        return SigningHeaders(
            api_version="v1",
            guid=_guid,
            r8id=base64.b64encode(r8id_ct).decode("ascii"),
            siv=base64.b64encode(_iv).decode("ascii"),
            ts=base64.b64encode(ts_ct).decode("ascii"),
        )

    def headers(self) -> dict[str, str]:
        return self.sign().as_dict()
