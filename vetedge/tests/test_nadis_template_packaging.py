from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_template_packager_is_parseable_and_fail_closed():
    source = _text("scripts/package_nadis_templates.py")
    ast.parse(source)

    assert "458e7af8b47c491f5245f5fc6cc8bbe754bbc23ab63829e88bb2083b813c05ba" in source
    assert "8ea90b4b5c30a66029186905e9aab846bf897f40121d5ec7d7d69acf2964db94" in source
    assert "base64.b64encode" in source
    assert "base64.b64decode" in source
    assert "validate=True" in source
    assert "Refusing to package" in source


def test_runtime_loader_supports_exact_raw_or_transport_safe_assets_and_sha256_verification():
    source = _text("vetedge/services/nadis_template_loader.py")
    ast.parse(source)

    assert "_raw_asset_path" in source
    assert "_base64_asset_path" in source
    assert "_multipart_base64_paths" in source
    assert 'glob(f"{filename}.b64.part*")' in source
    assert "base64.b64decode" in source
    assert "validate=True" in source
    assert "hashlib.sha256" in source
    assert "failed SHA-256 verification" in source
    assert "Regulatory export is blocked" in source


def test_runtime_loader_prefers_exact_raw_binary_when_available():
    source = _text("vetedge/services/nadis_template_loader.py")
    raw_index = source.index("if raw_path.exists()")
    base64_index = source.index("if base64_path.exists()")
    parts_index = source.index("if parts:")

    assert raw_index < base64_index < parts_index
