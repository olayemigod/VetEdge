from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services.portal_access import require_internal_user
from vetedge.services.report_visibility import normalize_report_filters


DOCTYPE = "Veterinary Patient"
PAGE_LENGTH_MAX = 100


def _filters(value: str | dict | None) -> dict:
    if not value:
        value = {}
    parsed = value if isinstance(value, dict) else frappe.parse_json(value)
    if not isinstance(parsed, dict):
        frappe.throw(_("Expected report filters as a JSON object."), frappe.ValidationError)
    cleaned = {key: item for key, item in parsed.items() if item not in (None, "")}
    if cleaned.get("customer") and not cleaned.get("owner"):
        cleaned["owner"] = cleaned.get("customer")
    return dict(normalize_report_filters("Patient Register", cleaned) or {})


def _require_read_permission() -> None:
    if not frappe.has_permission(DOCTYPE, "read"):
        frappe.throw(_("You do not have permission to view veterinary patients."), frappe.PermissionError)


def _query_filters(report_filters: dict) -> dict:
    filters = {}
    mappings = {
        "branch": "default_branch",
        "owner": "primary_owner",
        "species": "species",
        "breed": "breed",
        "registration_status": "registration_status",
        "status": "status",
    }
    for source, target in mappings.items():
        if report_filters.get(source):
            filters[target] = report_filters.get(source)
    return filters


def _columns() -> list[dict]:
    return [
        {"fieldname": "patient", "label": _("Patient"), "fieldtype": "Link", "options": DOCTYPE},
        {"fieldname": "patient_name", "label": _("Patient Name"), "fieldtype": "Data"},
        {"fieldname": "primary_owner", "label": _("Primary Owner"), "fieldtype": "Link", "options": "Customer"},
        {"fieldname": "species", "label": _("Species"), "fieldtype": "Link", "options": "Veterinary Species"},
        {"fieldname": "breed", "label": _("Breed"), "fieldtype": "Link", "options": "Veterinary Breed"},
        {"fieldname": "default_branch", "label": _("Default Branch"), "fieldtype": "Link", "options": "Branch"},
        {"fieldname": "registration_status", "label": _("Registration Status"), "fieldtype": "Data"},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data"},
        {"fieldname": "created_on", "label": _("Created On"), "fieldtype": "Datetime"},
    ]


def _status_counts(query_filters: dict) -> dict[str, int]:
    rows = frappe.get_all(
        DOCTYPE,
        filters=query_filters,
        fields=["status", {"COUNT": "name", "as": "row_count"}],
        group_by="status",
    )
    return {cstr(row.get("status") or _("Unspecified")): cint(row.get("row_count")) for row in rows}


def _species_count(query_filters: dict) -> int:
    species_filters = dict(query_filters)
    species_filters["species"] = ["is", "set"]
    rows = frappe.get_all(
        DOCTYPE,
        filters=species_filters,
        fields=["species"],
        group_by="species",
        page_length=500,
    )
    return len(rows)


def _summary(query_filters: dict, total: int) -> list[dict]:
    counts = _status_counts(query_filters)
    active = counts.get("Active", 0)
    inactive = counts.get("Inactive", 0)
    deceased = counts.get("Deceased", 0)
    return [
        {"label": _("Patients"), "value": total, "indicator": "Blue", "datatype": "Int"},
        {"label": _("Active"), "value": active, "indicator": "Green", "datatype": "Int"},
        {"label": _("Inactive"), "value": inactive, "indicator": "Orange", "datatype": "Int"},
        {"label": _("Deceased"), "value": deceased, "indicator": "Red", "datatype": "Int"},
        {"label": _("Species Represented"), "value": _species_count(query_filters), "indicator": "Blue", "datatype": "Int"},
    ]


@frappe.whitelist()
@frappe.read_only()
def get_patient_register_view(
    filters: str | dict | None = None,
    start: int = 0,
    page_length: int = 50,
) -> dict:
    require_internal_user()
    _require_read_permission()
    report_filters = _filters(filters)
    query_filters = _query_filters(report_filters)
    start = max(cint(start), 0)
    page_length = min(max(cint(page_length) or 50, 1), PAGE_LENGTH_MAX)

    total = cint(frappe.db.count(DOCTYPE, filters=query_filters))
    rows = frappe.get_all(
        DOCTYPE,
        filters=query_filters,
        fields=[
            "name",
            "patient_name",
            "primary_owner",
            "species",
            "breed",
            "default_branch",
            "registration_status",
            "status",
            "creation",
        ],
        order_by="creation desc, name desc",
        limit_start=start,
        limit_page_length=page_length,
    )
    data = [
        {
            "patient": row.get("name"),
            "patient_name": row.get("patient_name") or row.get("name"),
            "primary_owner": row.get("primary_owner"),
            "species": row.get("species"),
            "breed": row.get("breed"),
            "default_branch": row.get("default_branch"),
            "registration_status": row.get("registration_status"),
            "status": row.get("status"),
            "created_on": row.get("creation"),
        }
        for row in rows
    ]
    return {
        "title": _("Patient Register"),
        "columns": _columns(),
        "rows": data,
        "summary": _summary(query_filters, total),
        "chart": None,
        "message": "",
        "total": total,
        "start": start,
        "page_length": page_length,
        "metadata": {
            "pagination_mode": "query-level",
            "detail_rows_materialized": False,
            "summary_mode": "database-aggregate",
            "source": "patient-register",
        },
    }
