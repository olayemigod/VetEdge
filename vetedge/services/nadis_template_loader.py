from __future__ import annotations

import base64
import hashlib
import re
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
_PART_SUFFIX = re.compile(r"\.part(\d+)$")


def _asset_directory() -> Path:
    return Path(frappe.get_app_path("vetedge", "templates", "nadis"))


def _single_asset_path(filename: str) -> Path:
    return _asset_directory() / f"{filename}.b64"


def _multipart_asset_paths(filename: str) -> list[Path]:
    directory = _asset_directory()
    prefix = f"{filename}.b64.part"
    return sorted(path for path in directory.glob(f"{filename}.b64.part*") if path.name.startswith(prefix))


def _encoded_template_payload(filename: str) -> bytes:
    single = _single_asset_path(filename)
    parts = _multipart_asset_paths(filename)

    if single.exists() and parts:
        frappe.throw(
            _("Packaged NADIS template {0} has both single-file and multipart assets. Regulatory export is blocked.").format(filename),
            frappe.ValidationError,
        )

    if single.exists():
        return single.read_bytes().strip()

    if not parts:
        frappe.throw(
            _("Packaged NADIS template {0} is missing. Regulatory export is blocked.").format(filename),
            frappe.ValidationError,
        )

    indexed_parts: list[tuple[int, Path]] = []
    for path in parts:
        match = _PART_SUFFIX.search(path.name)
        if not match:
            frappe.throw(
                _("Packaged NADIS template {0} contains an invalid multipart filename. Regulatory export is blocked.").format(filename),
                frappe.ValidationError,
            )
        indexed_parts.append((int(match.group(1)), path))

    indexed_parts.sort(key=lambda item: item[0])
    indexes = [index for index, _path in indexed_parts]
    expected = list(range(len(indexed_parts)))
    if indexes != expected:
        frappe.throw(
            _("Packaged NADIS template {0} has missing or out-of-sequence multipart assets. Regulatory export is blocked.").format(filename),
            frappe.ValidationError,
        )

    return b"".join(path.read_bytes().strip() for _index, path in indexed_parts)


def load_verified_template_bytes(filename: str) -> bytes:
    expected_hash = _TEMPLATE_HASHES.get(filename)
    if not expected_hash:
        frappe.throw(_("Unsupported NADIS template: {0}").format(filename), frappe.ValidationError)

    encoded = _encoded_template_payload(filename)
    try:
        payload = base64.b64decode(encoded, validate=True)
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
        frappe.throw(_("openpyxl is required to inspect NADIS regulatory workbooks."))

    return load_workbook(BytesIO(load_verified_template_bytes(filename)), keep_links=True)
