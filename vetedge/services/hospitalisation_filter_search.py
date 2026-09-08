from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services.hospitalisation import assert_hospitalisation_enabled
from vetedge.services.portal_access import require_internal_user
from vetedge.services.report_visibility import normalize_report_filters


DOCTYPE = "Veterinary Hospitalisation"
MAX_PAGE_LENGTH = 20
CANDIDATE_WINDOW = 60
FIELDS = {"branch", "patient", "customer", "practitioner", "care_location"}
ACTIVE_STATUSES = ("Admitted", "Under Care", "Ready for Discharge")


def _clean_filters(filters) -> dict:
    if not filters:
        return {}
    value = frappe.parse_json(filters) if isinstance(filters, str) else filters
    if not isinstance(value, dict):
        frappe.throw(_("Expected Hospitalisation filters as a JSON object."), frappe.ValidationError)
    return {key: item for key, item in value.items() if item not in (None, "")}


def _normalized(filters) -> dict:
    cleaned = _clean_filters(filters)
    if cleaned.get("customer") and not cleaned.get("owner"):
        cleaned["owner"] = cleaned.get("customer")
    return dict(normalize_report_filters("Active Hospitalisations", cleaned) or {})


def _option(value, label=None) -> dict:
    value = cstr(value or "").strip()
    return {"value": value, "label": cstr(label or value).strip() or value}


def _bounded(value) -> int:
    return min(max(cint(value) or MAX_PAGE_LENGTH, 1), MAX_PAGE_LENGTH)


def _base_filters(normalized: dict, current_field: str) -> dict:
    field_map = {
        "branch": "service_branch",
        "patient": "patient",
        "customer": "customer",
        "practitioner": "attending_veterinarian",
        "care_location": "care_location",
        "status": "status",
        "care_level": "care_level",
        "invoice_status": "invoice_status",
        "payment_gate_status": "payment_gate_status",
        "company": "company",
    }
    output = {}
    for source, target in field_map.items():
        if source == current_field:
            continue
        value = normalized.get("owner") if source == "customer" else normalized.get(source)
        if value:
            output[target] = value
    if "status" not in output:
        output["status"] = ["in", list(ACTIVE_STATUSES)]
    return output


def _distinct_parent_values(fieldname: str, normalized: dict, current_field: str) -> list[str]:
    rows = frappe.get_list(
        DOCTYPE,
        filters=_base_filters(normalized, current_field),
        fields=[fieldname],
        group_by=fieldname,
        order_by=f"{fieldname} asc",
        page_length=CANDIDATE_WINDOW,
    )
    return [cstr(row.get(fieldname)).strip() for row in rows if cstr(row.get(fieldname)).strip()]


def _search_named_master(
    doctype: str,
    names: list[str],
    txt: str,
    start: int,
    page_length: int,
    label_field: str | None = None,
) -> list[dict]:
    if not names or not frappe.has_permission(doctype, "read"):
        return []
    fields = ["name"]
    if label_field:
        fields.append(label_field)
    filters = {"name": ["in", names]}
    or_filters = []
    if txt:
        pattern = f"%{txt}%"
        or_filters.append([doctype, "name", "like", pattern])
        if label_field:
            or_filters.append([doctype, label_field, "like", pattern])
    rows = frappe.get_list(
        doctype,
        fields=fields,
        filters=filters,
        or_filters=or_filters,
        order_by=f"{label_field or 'name'} asc, name asc" if label_field else "name asc",
        start=start,
        page_length=page_length,
    )
    return [_option(row.get("name"), row.get(label_field) if label_field else row.get("name")) for row in rows]


def _search_branch(txt: str, start: int, page_length: int, normalized: dict) -> list[dict]:
    names = _distinct_parent_values("service_branch", normalized, "branch")
    return _search_named_master("Branch", names, txt, start, page_length)


def _search_patient(txt: str, start: int, page_length: int, normalized: dict) -> list[dict]:
    names = _distinct_parent_values("patient", normalized, "patient")
    return _search_named_master("Veterinary Patient", names, txt, start, page_length, "patient_name")


def _search_customer(txt: str, start: int, page_length: int, normalized: dict) -> list[dict]:
    names = _distinct_parent_values("customer", normalized, "customer")
    return _search_named_master("Customer", names, txt, start, page_length, "customer_name")


def _search_practitioner(txt: str, start: int, page_length: int, normalized: dict) -> list[dict]:
    names = _distinct_parent_values("attending_veterinarian", normalized, "practitioner")
    return _search_named_master("User", names, txt, start, page_length, "full_name")


def _search_care_location(txt: str, start: int, page_length: int, normalized: dict) -> list[dict]:
    names = _distinct_parent_values("care_location", normalized, "care_location")
    return _search_named_master("Veterinary Care Location", names, txt, start, page_length, "location_name")


@frappe.whitelist()
@frappe.read_only()
def search_hospitalisation_filter_options(
    field: str,
    txt: str = "",
    start: int = 0,
    page_length: int = MAX_PAGE_LENGTH,
    filters=None,
) -> list[dict]:
    require_internal_user()
    assert_hospitalisation_enabled()
    if not frappe.has_permission(DOCTYPE, "read"):
        frappe.throw(_("You do not have permission to view Hospitalisations."), frappe.PermissionError)

    field = cstr(field or "").strip()
    if field not in FIELDS:
        frappe.throw(_("This Hospitalisation filter is not available."), frappe.PermissionError)

    normalized = _normalized(filters)
    txt = cstr(txt or "").strip()
    start = max(cint(start), 0)
    page_length = _bounded(page_length)

    searcher = {
        "branch": _search_branch,
        "patient": _search_patient,
        "customer": _search_customer,
        "practitioner": _search_practitioner,
        "care_location": _search_care_location,
    }[field]
    return searcher(txt, start, page_length, normalized)
