from __future__ import annotations

import base64
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "templates" / "nadis"

VACCINATION_FILENAME = "Nadis Template Vaccination Report 1.xlsx"
VACCINATION_SHA256 = "458e7af8b47c491f5245f5fc6cc8bbe754bbc23ab63829e88bb2083b813c05ba"


def _multipart_payload(filename: str) -> bytes:
    parts = sorted(ASSET_DIR.glob(f"{filename}.b64.part*"))
    assert parts, f"Packaged NADIS template parts are missing for {filename}"
    expected_names = [f"{filename}.b64.part{index:02d}" for index in range(len(parts))]
    assert [part.name for part in parts] == expected_names
    encoded = b"".join(part.read_bytes() for part in parts)
    return base64.b64decode(encoded, validate=True)


def test_packaged_vaccination_template_is_exact_authoritative_workbook():
    payload = _multipart_payload(VACCINATION_FILENAME)

    assert len(payload) == 41457
    assert hashlib.sha256(payload).hexdigest() == VACCINATION_SHA256
    assert payload.startswith(b"PK\x03\x04")
