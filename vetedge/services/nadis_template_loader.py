from __future__ import annotations

import base64
import hashlib
from io import BytesIO
from pathlib import Path

import frappe
from frappe import _

from vetedge.services.nadis_templates import (
    DISEASE_OUTBREAK_TEMPLATE_FILENAME,
    DISEASE_OUTBREAK_TEMPLATE_SHA256,
    VACCINATION_TEMPLATE_FILENAME,
    VACCINATION_TEMPLATE_SHA256,
)


_TEMPLATE_HASHES = {
    VACCINATION_TEMPLATE_FILENAME: VACCINATION_TEMPLATE_SHA256,
    DISEASE_OUTBREAK_TEMPLATE_FILENAME: DISEASE_OUTBREAK_TEMPLATE_SHA256,
}


def _asset_directory() -> Path:
    return Path(frappe.get_app_path("vetedge", "templates", "nadis"))


def _raw_asset_path(filename: str) -> Path:
    return _asset_directory() / filename


def _base64_asset_path(filename: str) -> Path:
    return _asset_directory() / f"{filename}.b64"


def _multipart_base64_paths(filename: str) -> list[Path]:
    directory = _asset_directory()
    return sorted(directory.glob(f"{filename}.b64.part*")) if directory.exists() else []


def _decode_base64_payload(encoded: bytes, filename: str) -> bytes:
    try:
        return base64.b64decode(encoded, validate=True)
    except Exception:
        frappe.throw(
            _("Packaged NADIS template {0} is not valid base64. Regulatory export is blocked.").format(filename),
            frappe.ValidationError,
        )


def _read_packaged_bytes(filename: str) -> bytes:
    raw_path = _raw_asset_path(filename)
    if raw_path.exists():
        return raw_path.read_bytes()

    base64_path = _base64_asset_path(filename)
    if base64_path.exists():
        return _decode_base64_payload(base64_path.read_bytes(), filename)

    parts = _multipart_base64_paths(filename)
    if parts:
        encoded = b"".join(path.read_bytes() for path in parts)
        return _decode_base64_payload(encoded, filename)

    frappe.throw(
        _("Packaged NADIS template {0} is missing. Regulatory export is blocked.").format(filename),
        frappe.ValidationError,
    )


def load_verified_template_bytes(filename: str) -> bytes:
    expected_hash = _TEMPLATE_HASHES.get(filename)
    if not expected_hash:
        frappe.throw(_("Unsupported NADIS template: {0}").format(filename), frappe.ValidationError)

    payload = _read_packaged_bytes(filename)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected_hash:
        frappe.throw(
            _("Packaged NADIS template {0} failed SHA-256 verification. Regulatory export is blocked.").format(filename),
            frappe.ValidationError,
        )
    return payload


def load_verified_workbook(filename: str):
    try:
        from openpyxl import load_workbook
    except ImportError:
        frappe.throw(_("openpyxl is required to generate NADIS regulatory workbooks."))

    return load_workbook(BytesIO(load_verified_template_bytes(filename)), keep_links=True)
