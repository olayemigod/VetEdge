from __future__ import annotations

from collections.abc import Iterable

import frappe
from frappe import _

from vetedge.services.portal_access import require_internal_user


def normalize_names(names: str | Iterable[str] | None) -> list[str]:
    if not names:
        return []
    if isinstance(names, str):
        try:
            parsed = frappe.parse_json(names)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            names = parsed
        else:
            names = [names]
    return list(dict.fromkeys(str(name).strip() for name in names if str(name).strip()))


def get_patient_display_map(names: str | Iterable[str] | None) -> dict[str, str]:
    patient_names = normalize_names(names)
    if not patient_names:
        return {}
    rows = frappe.get_list(
        "Veterinary Patient",
        filters={"name": ["in", patient_names]},
        fields=["name", "patient_name"],
        page_length=min(len(patient_names), 500),
    )
    return {row.name: row.patient_name or row.name for row in rows}


@frappe.whitelist()
def get_patient_labels(names: str | list[str] | None = None) -> dict[str, str]:
    require_internal_user()
    requested = normalize_names(names)
    if len(requested) > 500:
        frappe.throw(_("Patient display-name requests are limited to 500 records."), frappe.ValidationError)
    return get_patient_display_map(requested)
