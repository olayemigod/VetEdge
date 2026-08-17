from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from vetedge.services.portal_access import require_internal_user
from vetedge.services.report_visibility import normalize_report_filters
from vetedge.services.reporting_structure import (
    _date_filter_dict,
    _get_consultation_invoice_map,
    _get_consultation_planned_totals,
    _get_consultation_vaccination_counts,
    _get_invoice_status_map,
    _get_patient_title_map,
    _get_user_full_name_map,
    _plain_text,
)


DOCTYPE = "Veterinary Consultation"
PAGE_LENGTH_MAX = 100
ACTIVE_STATUSES = {"Draft", "In Progress", "Awaiting Payment", "Pending Dispensary", "Ready for Treatment"}
COMPLETED_STATUSES = {"Completed"}
CANCELLED_STATUSES = {"Cancelled"}


def _filters(value: str | dict | None) -> dict:
    if not value:
        value = {}
    parsed = value if isinstance(value, dict) else frappe.parse_json(value)
    if not isinstance(parsed, dict):
        frappe.throw(_("Expected report filters as a JSON object."), frappe.ValidationError)
    cleaned = {key: item for key, item in parsed.items() if item not in (None, "")}
    if cleaned.get("customer") and not cleaned.get("owner"):
        cleaned["owner"] = cleaned.get("customer")
    return dict(normalize_report_filters("Consultation Register", cleaned) or {})


def _require_read_permission() -> None:
    if not frappe.has_permission(DOCTYPE, "read"):
        frappe.throw(_("You do not have permission to view consultations."), frappe.PermissionError)


def _query_filters(report_filters: dict) -> dict:
    filters = _date_filter_dict("consultation_datetime", frappe._dict(report_filters), 30)
    mappings = {
        "branch": "service_branch",
        "practitioner": "consulting_practitioner",
        "status": "status",
        "consultation_status": "status",
        "patient": "patient",
        "owner": "primary_owner",
        "consultation_type": "consultation_type",
        "payment_status": "payment_status",
        "created_by": "owner",
    }
    for source, target in mappings.items():
        if report_filters.get(source):
            filters[target] = report_filters.get(source)
    return filters


def _follow_up_or_filters(report_filters: dict) -> list[dict] | None:
    value = report_filters.get("has_follow_up")
    if value in (1, "1", "Yes"):
        return [{"follow_up_date": ("is", "set")}, {"follow_up_appointment": ("is", "set")}]
    return None


def _needs_no_follow_up(report_filters: dict) -> bool:
    return report_filters.get("has_follow_up") in (0, "0", "No")


def _vaccination_consultation_names(wants_vaccination: bool) -> list[str] | None:
    if not frappe.db.exists("DocType", "Veterinary Vaccination Record"):
        return [] if wants_vaccination else None
    names = {
        cstr(value).strip()
        for value in frappe.get_all(
            "Veterinary Vaccination Record",
            filters={"linked_consultation": ("is", "set")},
            pluck="linked_consultation",
        )
        if cstr(value).strip()
    }
    return sorted(names)


def _apply_special_filters(query_filters: dict, report_filters: dict) -> dict:
    filters = dict(query_filters)
    if _needs_no_follow_up(report_filters):
        filters["follow_up_date"] = ("is", "not set")
        filters["follow_up_appointment"] = ("is", "not set")
    if report_filters.get("has_vaccination") in (1, "1", "Yes", 0, "0", "No"):
        wants = report_filters.get("has_vaccination") in (1, "1", "Yes")
        linked_names = _vaccination_consultation_names(wants)
        if wants:
            filters["name"] = ("in", linked_names or ["__vetedge_no_matching_consultation__"])
        elif linked_names:
            filters["name"] = ("not in", linked_names)
    return filters


def _columns() -> list[dict]:
    return [
        {"fieldname": "consultation", "label": _("Consultation"), "fieldtype": "Link", "options": DOCTYPE},
        {"fieldname": "consultation_datetime", "label": _("Consultation Date/Time"), "fieldtype": "Datetime"},
        {"fieldname": "service_branch", "label": _("Service Branch"), "fieldtype": "Link", "options": "Branch"},
        {"fieldname": "patient", "label": _("Patient / Animal"), "fieldtype": "Data"},
        {"fieldname": "owner", "label": _("Owner / Customer"), "fieldtype": "Link", "options": "Customer"},
        {"fieldname": "practitioner", "label": _("Practitioner"), "fieldtype": "Data"},
        {"fieldname": "consultation_type", "label": _("Consultation Type"), "fieldtype": "Link", "options": "Consultation Type"},
        {"fieldname": "linked_appointment", "label": _("Appointment"), "fieldtype": "Link", "options": "Veterinary Appointment"},
        {"fieldname": "status", "label": _("Status / Workflow State"), "fieldtype": "Data"},
        {"fieldname": "invoice", "label": _("Invoice"), "fieldtype": "Link", "options": "Sales Invoice"},
        {"fieldname": "invoice_status", "label": _("Invoice Status"), "fieldtype": "Data"},
        {"fieldname": "payment_status", "label": _("Payment Status"), "fieldtype": "Data"},
        {"fieldname": "planned_treatment_total", "label": _("Planned Treatment Total"), "fieldtype": "Currency"},
        {"fieldname": "vaccination_count", "label": _("Vaccination Count"), "fieldtype": "Int"},
        {"fieldname": "has_vaccination", "label": _("Has Vaccination"), "fieldtype": "Data"},
        {"fieldname": "follow_up_date", "label": _("Follow-up Date"), "fieldtype": "Date"},
        {"fieldname": "next_appointment", "label": _("Next Appointment"), "fieldtype": "Link", "options": "Veterinary Appointment"},
        {"fieldname": "outcome_assessment_summary", "label": _("Outcome / Assessment Summary"), "fieldtype": "Data"},
        {"fieldname": "created_by", "label": _("Created By"), "fieldtype": "Data"},
    ]


def _page_rows(filters: dict, or_filters: list[dict] | None, start: int, page_length: int):
    kwargs = {
        "doctype": DOCTYPE,
        "filters": filters,
        "fields": [
            "name",
            "consultation_datetime",
            "service_branch",
            "patient",
            "primary_owner",
            "consulting_practitioner",
            "consulting_practitioner_name",
            "consultation_type",
            "linked_appointment",
            "status",
            "linked_invoice",
            "payment_status",
            "follow_up_date",
            "follow_up_appointment",
            "assessment_notes",
            "owner",
        ],
        "order_by": "consultation_datetime desc, name desc",
        "limit_start": start,
        "limit_page_length": page_length,
    }
    if or_filters:
        kwargs["or_filters"] = or_filters
    return frappe.get_all(**kwargs)


def _matching_names(filters: dict, or_filters: list[dict] | None) -> list[str]:
    kwargs = {"doctype": DOCTYPE, "filters": filters, "pluck": "name"}
    if or_filters:
        kwargs["or_filters"] = or_filters
    return frappe.get_all(**kwargs)


def _status_counts(filters: dict, or_filters: list[dict] | None) -> dict[str, int]:
    kwargs = {
        "doctype": DOCTYPE,
        "filters": filters,
        "fields": ["status", {"COUNT": "name", "as": "row_count"}],
        "group_by": "status",
    }
    if or_filters:
        kwargs["or_filters"] = or_filters
    rows = frappe.get_all(**kwargs)
    return {cstr(row.get("status")): cint(row.get("row_count")) for row in rows}


def _aggregate_planned_total(consultation_names: list[str]) -> float:
    names = [name for name in consultation_names if name]
    if not names or not frappe.db.exists("DocType", "Planned Treatment Item"):
        return 0.0
    rows = frappe.get_all(
        "Planned Treatment Item",
        filters={"parent": ("in", names), "parenttype": DOCTYPE},
        fields=[{"SUM": "amount", "as": "planned_total"}],
    )
    return flt(rows[0].get("planned_total")) if rows else 0.0


def _summary(filters: dict, or_filters: list[dict] | None, total: int) -> list[dict]:
    counts = _status_counts(filters, or_filters)
    completed = sum(counts.get(status, 0) for status in COMPLETED_STATUSES)
    active = sum(counts.get(status, 0) for status in ACTIVE_STATUSES)
    cancelled = sum(counts.get(status, 0) for status in CANCELLED_STATUSES)
    awaiting_payment = counts.get("Awaiting Payment", 0)
    names = _matching_names(filters, or_filters)
    planned_total = _aggregate_planned_total(names)
    follow_up_filters = dict(filters)
    follow_up_or = [{"follow_up_date": ("is", "set")}, {"follow_up_appointment": ("is", "set")}]
    follow_up_count = len(_matching_names(follow_up_filters, follow_up_or))
    return [
        {"label": _("Total Consultations"), "value": total, "indicator": "Blue", "datatype": "Int"},
        {"label": _("Completed"), "value": completed, "indicator": "Green", "datatype": "Int"},
        {"label": _("Active / In Progress"), "value": active, "indicator": "Orange", "datatype": "Int"},
        {"label": _("Awaiting Payment"), "value": awaiting_payment, "indicator": "Orange", "datatype": "Int"},
        {"label": _("Cancelled"), "value": cancelled, "indicator": "Red", "datatype": "Int"},
        {"label": _("Completion Rate"), "value": flt((completed / total) * 100, 1) if total else 0, "indicator": "Green", "datatype": "Percent"},
        {"label": _("Average Planned Value"), "value": flt(planned_total / total, 2) if total else 0, "indicator": "Blue", "datatype": "Currency"},
        {"label": _("Follow-up Required"), "value": follow_up_count, "indicator": "Purple", "datatype": "Int"},
    ]


def _chart(filters: dict, or_filters: list[dict] | None) -> dict | None:
    counts = _status_counts(filters, or_filters)
    labels = [status for status, value in sorted(counts.items()) if value]
    if not labels:
        return None
    return {
        "title": _("Consultations by Status"),
        "type": "bar",
        "data": {"labels": labels, "datasets": [{"name": _("Consultations"), "values": [counts[label] for label in labels]}]},
    }


def _render_rows(page_rows) -> list[dict]:
    names = [row.get("name") for row in page_rows if row.get("name")]
    patient_titles = _get_patient_title_map(row.get("patient") for row in page_rows)
    practitioner_names = _get_user_full_name_map(row.get("consulting_practitioner") for row in page_rows)
    invoice_map = _get_consultation_invoice_map(names)
    invoice_names = sorted(
        {
            invoice_name
            for row in page_rows
            for invoice_name in ([row.get("linked_invoice")] + invoice_map.get(row.get("name"), []))
            if invoice_name
        }
    )
    invoice_statuses = _get_invoice_status_map(invoice_names)
    planned_totals = _get_consultation_planned_totals(names)
    vaccination_counts = _get_consultation_vaccination_counts(names)
    output = []
    for row in page_rows:
        invoice = row.get("linked_invoice") or next(iter(invoice_map.get(row.get("name"), [])), None)
        vaccination_count = cint(vaccination_counts.get(row.get("name")))
        output.append(
            {
                "consultation": row.get("name"),
                "consultation_datetime": row.get("consultation_datetime"),
                "service_branch": row.get("service_branch"),
                "patient": patient_titles.get(row.get("patient")) or row.get("patient"),
                "owner": row.get("primary_owner"),
                "practitioner": practitioner_names.get(row.get("consulting_practitioner")) or row.get("consulting_practitioner_name") or row.get("consulting_practitioner"),
                "consultation_type": row.get("consultation_type"),
                "linked_appointment": row.get("linked_appointment"),
                "status": row.get("status"),
                "invoice": invoice,
                "invoice_status": invoice_statuses.get(invoice) or _("Not Billed"),
                "payment_status": row.get("payment_status") or _("Not Billed"),
                "planned_treatment_total": flt(planned_totals.get(row.get("name"))),
                "vaccination_count": vaccination_count,
                "has_vaccination": _("Yes") if vaccination_count else _("No"),
                "follow_up_date": row.get("follow_up_date"),
                "next_appointment": row.get("follow_up_appointment"),
                "outcome_assessment_summary": _plain_text(row.get("assessment_notes")),
                "created_by": row.get("owner"),
            }
        )
    return output


@frappe.whitelist()
@frappe.read_only()
def get_consultation_register_view(
    filters: str | dict | None = None,
    start: int = 0,
    page_length: int = 50,
) -> dict:
    require_internal_user()
    _require_read_permission()
    report_filters = _filters(filters)
    query_filters = _apply_special_filters(_query_filters(report_filters), report_filters)
    or_filters = _follow_up_or_filters(report_filters)
    start = max(cint(start), 0)
    page_length = min(max(cint(page_length) or 50, 1), PAGE_LENGTH_MAX)

    if not frappe.db.exists("DocType", DOCTYPE):
        return {
            "title": _("Consultation Register"),
            "columns": _columns(),
            "rows": [],
            "summary": [],
            "chart": None,
            "total": 0,
            "start": start,
            "page_length": page_length,
            "metadata": {"pagination_mode": "query-level", "detail_rows_materialized": False},
        }

    total = len(_matching_names(query_filters, or_filters))
    page_rows = _page_rows(query_filters, or_filters, start, page_length)
    return {
        "title": _("Consultation Register"),
        "columns": _columns(),
        "rows": _render_rows(page_rows),
        "summary": _summary(query_filters, or_filters, total),
        "chart": _chart(query_filters, or_filters),
        "message": "",
        "total": total,
        "start": start,
        "page_length": page_length,
        "metadata": {
            "pagination_mode": "query-level",
            "detail_rows_materialized": False,
            "enrichment_mode": "page-only",
            "summary_mode": "aggregate-plus-identifiers",
            "source": "consultation-register",
        },
    }
