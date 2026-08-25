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


def _asset_path(filename: str) -> Path:
    return Path(frappe.get_app_path("vetedge", "templates", "nadis", f"{filename}.b64"))


def load_verified_template_bytes(filename: str) -> bytes:
    expected_hash = _TEMPLATE_HASHES.get(filename)
    if not expected_hash:
        frappe.throw(_("Unsupported NADIS template: {0}").format(filename), frappe.ValidationError)

    path = _asset_path(filename)
    if not path.exists():
        frappe.throw(
            _("Packaged NADIS template {0} is missing. Regulatory export is blocked.").format(filename),
            frappe.ValidationError,
        )

    try:
        payload = base64.b64decode(path.read_bytes(), validate=True)
    except Exception as exc:
        frappe.throw(
            _("Packaged NADIS template {0} is not valid base64. Regulatory export is blocked.").format(filename),
            frappe.ValidationError,
        )
        raise exc

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
