from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services.portal_access import require_internal_user
from vetedge.services.report_visibility import normalize_report_filters
from vetedge.services.reporting_structure import _date_filter_dict, _get_user_full_name_map


VACCINATION_DOCTYPE = "Veterinary Vaccination Record"
PATIENT_DOCTYPE = "Veterinary Patient"
PAGE_LENGTH_MAX = 100


def _filters(value: str | dict | None) -> dict:
    if not value:
        value = {}
    parsed = value if isinstance(value, dict) else frappe.parse_json(value)
    if not isinstance(parsed, dict):
        frappe.throw(_("Expected regulatory report filters as a JSON object."), frappe.ValidationError)
    cleaned = {key: item for key, item in parsed.items() if item not in (None, "")}
    if cleaned.get("customer") and not cleaned.get("owner"):
        cleaned["owner"] = cleaned.get("customer")
    # Reuse the established Vaccination Report visibility contract until the
    # authoritative NADIS workbook mapping is recovered and a dedicated public
    # report name is exposed in the UI.
    return dict(normalize_report_filters("Vaccination Report", cleaned) or {})


def _require_permissions() -> None:
    require_internal_user()
    if not frappe.has_permission(VACCINATION_DOCTYPE, "read"):
        frappe.throw(_("You do not have permission to view vaccination records."), frappe.PermissionError)
    if not frappe.has_permission(PATIENT_DOCTYPE, "read"):
        frappe.throw(_("You do not have permission to view veterinary patients."), frappe.PermissionError)


def _query_filters(report_filters: dict) -> dict:
    # Use the same date normalization as the established VetEdge report
    # services so a selected end date includes the full reporting day for
    # Datetime fields rather than stopping at midnight.
    filters = _date_filter_dict("administered_on", frappe._dict(report_filters))
    mappings = {
        "branch": "service_branch",
        "patient": "patient",
        "owner": "primary_owner",
        "vaccine": "vaccine",
        "practitioner": "administered_by",
        "status": "status",
        "company": "company",
    }
    for source, target in mappings.items():
        if report_filters.get(source):
            filters[target] = report_filters.get(source)
    return filters


def _patient_map(patient_names: list[str]) -> dict[str, dict]:
    names = sorted({cstr(name).strip() for name in patient_names if cstr(name).strip()})
    if not names:
        return {}
    rows = frappe.get_list(
        PATIENT_DOCTYPE,
        filters={"name": ["in", names]},
        fields=["name", "patient_name", "primary_owner", "species", "breed"],
        page_length=min(len(names), PAGE_LENGTH_MAX),
    )
    return {row.get("name"): row for row in rows}


def _columns() -> list[dict]:
    # This is a normalized regulatory source dataset, not the final official
    # spreadsheet layout. Exact NADIS workbook headers/order remain a separate
    # verified template-mapping layer.
    return [
        {"fieldname": "vaccination_record", "label": _("Vaccination Record"), "fieldtype": "Link", "options": VACCINATION_DOCTYPE},
        {"fieldname": "administered_on", "label": _("Administered On"), "fieldtype": "Datetime"},
        {"fieldname": "service_branch", "label": _("Branch"), "fieldtype": "Link", "options": "Branch"},
        {"fieldname": "company", "label": _("Company"), "fieldtype": "Link", "options": "Company"},
        {"fieldname": "patient", "label": _("Patient"), "fieldtype": "Link", "options": PATIENT_DOCTYPE},
        {"fieldname": "patient_name", "label": _("Patient Name"), "fieldtype": "Data"},
        {"fieldname": "owner", "label": _("Owner"), "fieldtype": "Link", "options": "Customer"},
        {"fieldname": "species", "label": _("Species"), "fieldtype": "Link", "options": "Veterinary Species"},
        {"fieldname": "breed", "label": _("Breed"), "fieldtype": "Link", "options": "Veterinary Breed"},
        {"fieldname": "vaccine", "label": _("Vaccine"), "fieldtype": "Link", "options": "Veterinary Vaccine"},
        {"fieldname": "dose", "label": _("Dose"), "fieldtype": "Data"},
        {"fieldname": "route", "label": _("Route"), "fieldtype": "Data"},
        {"fieldname": "batch_no", "label": _("Batch No"), "fieldtype": "Link", "options": "Batch"},
        {"fieldname": "batch_expiry_date", "label": _("Batch Expiry Date"), "fieldtype": "Date"},
        {"fieldname": "administered_by", "label": _("Administered By"), "fieldtype": "Data"},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data"},
        {"fieldname": "next_due_date", "label": _("Next Due Date"), "fieldtype": "Datetime"},
    ]


def _summary(query_filters: dict, total: int) -> list[dict]:
    administered_filters = dict(query_filters)
    administered_filters["status"] = "Administered"
    cancelled_filters = dict(query_filters)
    cancelled_filters["status"] = "Cancelled"
    return [
        {"label": _("Records"), "value": total, "datatype": "Int"},
        {"label": _("Administered"), "value": cint(frappe.db.count(VACCINATION_DOCTYPE, administered_filters)), "datatype": "Int"},
        {"label": _("Cancelled"), "value": cint(frappe.db.count(VACCINATION_DOCTYPE, cancelled_filters)), "datatype": "Int"},
    ]


@frappe.whitelist()
@frappe.read_only()
def get_nadis_vaccination_source(
    filters: str | dict | None = None,
    start: int = 0,
    page_length: int = 50,
) -> dict:
    """Return a branch-safe, paginated vaccination source for NADIS mapping.

    The response is intentionally a normalized source dataset. It is not
    represented as the final official NADIS workbook until the authoritative
    spreadsheet headers/order/merges are verified against the supplied template.
    """
    _require_permissions()
    report_filters = _filters(filters)
    query_filters = _query_filters(report_filters)
    start = max(cint(start), 0)
    page_length = min(max(cint(page_length) or 50, 1), PAGE_LENGTH_MAX)

    total = cint(frappe.db.count(VACCINATION_DOCTYPE, filters=query_filters))
    source_rows = frappe.get_list(
        VACCINATION_DOCTYPE,
        filters=query_filters,
        fields=[
            "name",
            "patient",
            "primary_owner",
            "status",
            "service_branch",
            "company",
            "vaccine",
            "administered_by",
            "administered_on",
            "dose",
            "route",
            "next_due_date",
            "expiry_date",
            "batch_no",
        ],
        order_by="administered_on desc, name desc",
        start=start,
        page_length=page_length,
    )
    patients = _patient_map([row.get("patient") for row in source_rows])
    practitioner_names = _get_user_full_name_map(row.get("administered_by") for row in source_rows)

    rows = []
    for row in source_rows:
        patient = patients.get(row.get("patient")) or {}
        rows.append(
            {
                "vaccination_record": row.get("name"),
                "administered_on": row.get("administered_on"),
                "service_branch": row.get("service_branch"),
                "company": row.get("company"),
                "patient": row.get("patient"),
                "patient_name": patient.get("patient_name") or row.get("patient"),
                "owner": row.get("primary_owner") or patient.get("primary_owner"),
                "species": patient.get("species"),
                "breed": patient.get("breed"),
                "vaccine": row.get("vaccine"),
                "dose": row.get("dose"),
                "route": row.get("route"),
                "batch_no": row.get("batch_no"),
                "batch_expiry_date": row.get("expiry_date"),
                "administered_by": practitioner_names.get(row.get("administered_by")) or row.get("administered_by"),
                "status": row.get("status"),
                "next_due_date": row.get("next_due_date"),
            }
        )

    return {
        "title": _("NADIS Vaccination Source"),
        "subtitle": _("Normalized VetEdge vaccination data awaiting verified NADIS workbook column mapping."),
        "columns": _columns(),
        "rows": rows,
        "summary": _summary(query_filters, total),
        "chart": None,
        "message": "",
        "total": total,
        "start": start,
        "page_length": page_length,
        "has_previous": start > 0,
        "has_next": start + len(rows) < total,
        "metadata": {
            "pagination_mode": "query-level",
            "detail_rows_materialized": False,
            "regulatory_family": "NADIS",
            "regulatory_report": "vaccination",
            "template_mapping_verified": False,
            "submission_ready": False,
        },
    }
