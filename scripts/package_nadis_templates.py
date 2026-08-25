#!/usr/bin/env python3
"""Package the authoritative NADIS XLSX workbooks for VetEdge.

The GitHub contents API used by some development environments is text-only.
VetEdge therefore stores the official XLSX payloads as strict base64 assets and
verifies the decoded SHA-256 at runtime before regulatory export.

Usage:
    python scripts/package_nadis_templates.py \
        --vaccination '/path/Nadis Template Vaccination Report 1.xlsx' \
        --outbreak '/path/NadisTemplate Disease Outbreak Report.xlsx'

The script fails closed if either source file does not match the authoritative
hash recorded from the supplied workbooks.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
from pathlib import Path

VACCINATION_FILENAME = "Nadis Template Vaccination Report 1.xlsx"
VACCINATION_SHA256 = "458e7af8b47c491f5245f5fc6cc8bbe754bbc23ab63829e88bb2083b813c05ba"
OUTBREAK_FILENAME = "NadisTemplate Disease Outbreak Report.xlsx"
OUTBREAK_SHA256 = "8ea90b4b5c30a66029186905e9aab846bf897f40121d5ec7d7d69acf2964db94"

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET_DIR = REPO_ROOT / "vetedge" / "templates" / "nadis"


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _package(source: Path, filename: str, expected_hash: str) -> Path:
    payload = source.read_bytes()
    actual_hash = _digest(payload)
    if actual_hash != expected_hash:
        raise SystemExit(
            f"Refusing to package {source}: SHA-256 {actual_hash} does not match "
            f"authoritative {expected_hash}."
        )

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    target = TARGET_DIR / f"{filename}.b64"
    target.write_text(base64.b64encode(payload).decode("ascii"), encoding="ascii")

    decoded = base64.b64decode(target.read_bytes(), validate=True)
    if _digest(decoded) != expected_hash:
        raise SystemExit(f"Verification failed after writing {target}.")
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vaccination", type=Path, required=True)
    parser.add_argument("--outbreak", type=Path, required=True)
    args = parser.parse_args()

    outputs = (
        _package(args.vaccination, VACCINATION_FILENAME, VACCINATION_SHA256),
        _package(args.outbreak, OUTBREAK_FILENAME, OUTBREAK_SHA256),
    )
    for output in outputs:
        print(output.relative_to(REPO_ROOT))


if __name__ == "__main__":
    main()
