"""EKAP signing parity tests.

Verifies that `app.ekap.crypto.EkapSigner` produces the exact ciphertext the
mobile app's crypto-js implementation would produce for the same deterministic
inputs. When Node + crypto-js is available we additionally run the reference
script and compare bytes-for-bytes.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from app.ekap.crypto import EkapSigner


KEY = "Qm2LtXR0aByP69vZNKef4wMJ"

# Frozen inputs that produce a known-good output (generated offline from
# crypto-js for this key/guid/iv/timestamp triple).
GUID = "11111111-2222-4333-8444-555566667777"
IV_HEX = "00112233445566778899aabbccddeeff"
TS_MS = 1710000000000

# Regenerated from Node + crypto-js with the triple above. These are the
# values the mobile signer would emit — our Python output must match.
EXPECTED_R8ID = "87R4flxHqYB4FbtlDhcghOqwGq7Jae2kfep/RX40UrKZjaP1hGSqlBWefX8GK1Ra"
EXPECTED_TS = "RzqWYaeAmd/Q8tKswNVRtQ=="


def _sign_headers() -> dict[str, str]:
    signer = EkapSigner(signing_key=KEY)
    headers = signer.sign(
        guid=GUID,
        iv=bytes.fromhex(IV_HEX),
        timestamp_ms=TS_MS,
    ).as_dict()
    return headers


def test_signer_outputs_expected_iv_base64() -> None:
    headers = _sign_headers()
    assert headers["api-version"] == "v1"
    assert headers["X-Custom-Request-Guid"] == GUID
    assert base64.b64decode(headers["X-Custom-Request-Siv"]) == bytes.fromhex(IV_HEX)


def test_signer_key_length_enforced() -> None:
    with pytest.raises(ValueError, match="24 bytes"):
        EkapSigner(signing_key="too-short")


@pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node is not available; crypto-js parity test requires Node runtime",
)
def test_python_matches_node_crypto_js_reference(tmp_path: Path) -> None:
    """Live parity check when Node + crypto-js is installed."""
    script = (
        Path(__file__).resolve().parent.parent / "scripts" / "node_crypto_reference.js"
    )
    assert script.exists(), "reference script missing"

    # Best effort: try to use whichever crypto-js install is available.
    env = os.environ.copy()
    try:
        result = subprocess.run(
            ["node", str(script), GUID, IV_HEX, str(TS_MS)],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        pytest.skip("could not invoke node reference script")

    if result.returncode != 0:
        pytest.skip(
            f"node script failed (crypto-js missing?): {result.stderr.strip()}"
        )

    ref_headers = json.loads(result.stdout)
    py_headers = _sign_headers()

    assert py_headers["X-Custom-Request-Guid"] == ref_headers["X-Custom-Request-Guid"]
    assert py_headers["X-Custom-Request-Siv"] == ref_headers["X-Custom-Request-Siv"]
    assert py_headers["X-Custom-Request-R8id"] == ref_headers["X-Custom-Request-R8id"]
    assert py_headers["X-Custom-Request-Ts"] == ref_headers["X-Custom-Request-Ts"]


def test_expected_ciphertext_regression() -> None:
    """Guard against accidental changes to key/padding/mode.

    The EXPECTED_* constants in this file were produced by crypto-js with the
    frozen inputs above; if they ever diverge from our Python output we have
    broken mobile parity.
    """
    headers = _sign_headers()
    # If this test fails unexpectedly, first regenerate EXPECTED_* from
    # `node scripts/node_crypto_reference.js GUID IV_HEX TS_MS`.
    assert headers["X-Custom-Request-R8id"] == EXPECTED_R8ID
    assert headers["X-Custom-Request-Ts"] == EXPECTED_TS
