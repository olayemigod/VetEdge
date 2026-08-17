from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from vetedge.services.portal_access import require_internal_user
from vetedge.services.report_visibility import normalize_report_filters
from vetedge.services.reporting_structure import _date_filter_dict, _get_patient_title_map, _get_user_full_name_map


DOCTYPE = "Veterinary Lab Order"
ITEM_DOCTYPE = "Veterinary Lab Order Item"
PAGE_LENGTH_MAX = 100
PENDING_STATUSES = {"Draft", "Ordered"}
IN_PROGRESS_STATUSES = {"Sample Collected", "Sent to Lab", "In Progress", "Result Pending", "Result Entered", "Awaiting Review"}
COMPLETED_STATUSES = {"Reviewed", "Completed"}
CANCELLED_STATUSES = {"Cancelled"}


def _filters(value: str | dict | None) -> dict:
    if not value:
        value = {}
    parsed = value if isinstance(value, dict) else frappe.parse_json(value)
    if not isinstance(parsed, dict):
        frappe.throw(_("Expected report filters as a JSON object."), frappe.ValidationError)
    cleaned = {key: item for key, item in parsed.items() if item not in (None, "")}
    return dict(normalize_report_filters("Lab Order Report", cleaned) or {})


def _require_read_permission() -> None:
    if not frappe.has_permission(DOCTYPE, "read"):
        frappe.throw(_("You do not have permission to view laboratory orders."), frappe.PermissionError)


def _query_filters(report_filters: dict) -> dict:
    filters = _date_filter_dict("requested_on", frappe._dict(report_filters), 30)
    if report_filters.get("branch"):
        filters["service_branch"] = report_filters.get("branch")
    if report_filters.get("status"):
        filters["status"] = report_filters.get("status")
    requested_by = report_filters.get("requested_by") or report_filters.get("practitioner")
    if requested_by:
        filters["requested_by"] = requested_by
    if report_filters.get("patient"):
        filters["patient"] = report_filters.get("patient")
    if report_filters.get("owner"):
        filters["primary_owner"] = report_filters.get("owner")
    return filters


def _columns() -> list[dict]:
    return [
        {"fieldname": "lab_order", "label": _("Lab Order"), "fieldtype": "Link", "options": DOCTYPE},
        {"fieldname": "patient", "label": _("Patient"), "fieldtype": "Data"},
        {"fieldname": "owner", "label": _("Owner"), "fieldtype": "Link", "options": "Customer"},
        {"fieldname": "consultation", "label": _("Consultation"), "fieldtype": "Link", "options": "Veterinary Consultation"},
        {"fieldname": "service_branch", "label": _("Service Branch"), "fieldtype": "Link", "options": "Branch"},
        {"fieldname": "requested_by", "label": _("Requested By"), "fieldtype": "Data"},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data"},
        {"fieldname": "requested_on", "label": _("Requested On"), "fieldtype": "Datetime"},
        {"fieldname": "result_entered_on", "label": _("Result Entered On"), "fieldtype": "Datetime"},
        {"fieldname": "reviewed_on", "label": _("Reviewed On"), "fieldtype": "Datetime"},
        {"fieldname": "linked_invoice", "label": _("Linked Invoice"), "fieldtype": "Link", "options": "Sales Invoice"},
    ]


def _page_result_entered_map(order_names: list[str]) -> dict[str, object]:
    names = sorted({cstr(name).strip() for name in order_names if cstr(name).strip()})
    if not names or not frappe.db.exists("DocType", ITEM_DOCTYPE):
        return {}
    rows = frappe.get_all(
        ITEM_DOCTYPE,
        filters={"parent": ("in", names), "entered_on": ("is", "set")},
        fields=["parent", {"MAX": "entered_on", "as": "result_entered_on"}],
        group_by="parent",
    )
    return {row.get("parent"): row.get("result_entered_on") for row in rows}


def _status_counts(query_filters: dict) -> dict[str, int]:
    rows = frappe.get_all(
        DOCTYPE,
        filters=query_filters,
        fields=["status", {"COUNT": "name", "as": "row_count"}],
        group_by="status",
    )
    return {cstr(row.get("status")): cint(row.get("row_count")) for row in rows}


def _summary(query_filters: dict, total: int) -> tuple[list[dict], dict]:
    counts = _status_counts(query_filters)
    pending = sum(counts.get(status, 0) for status in PENDING_STATUSES)
    in_progress = sum(counts.get(status, 0) for status in IN_PROGRESS_STATUSES)
    completed = sum(counts.get(status, 0) for status in COMPLETED_STATUSES)
    cancelled = sum(counts.get(status, 0) for status in CANCELLED_STATUSES)
    unbilled_filters = dict(query_filters)
    unbilled_filters["linked_invoice"] = ("is", "not set")
    unbilled = frappe.db.count(DOCTYPE, filters=unbilled_filters)
    cards = [
        {"label": _("Total Lab Orders"), "value": total, "indicator": "Blue", "datatype": "Int"},
        {"label": _("Pending"), "value": pending, "indicator": "Orange", "datatype": "Int"},
        {"label": _("In Progress"), "value": in_progress, "indicator": "Blue", "datatype": "Int"},
        {"label": _("Completed / Reviewed"), "value": completed, "indicator": "Green", "datatype": "Int"},
        {"label": _("Cancelled"), "value": cancelled, "indicator": "Red", "datatype": "Int"},
        {"label": _("Unbilled"), "value": cint(unbilled), "indicator": "Orange", "datatype": "Int"},
        {
            "label": _("Completion Rate"),
            "value": flt((completed / total) * 100, 1) if total else 0,
            "indicator": "Green",
            "datatype": "Percent",
        },
    ]
    return cards, counts


def _chart(counts: dict[str, int]) -> dict | None:
    labels = [label for label, value in sorted(counts.items()) if value]
    if not labels:
        return None
    return {
        "title": _("Lab Orders by Status"),
        "type": "bar",
        "data": {"labels": labels, "datasets": [{"name": _("Orders"), "values": [counts[label] for label in labels]}]},
    }


def _render_rows(page_rows) -> list[dict]:
    patient_ids = {row.get("patient") for row in page_rows if row.get("patient")}
    requester_ids = {row.get("requested_by") for row in page_rows if row.get("requested_by")}
    patient_titles = _get_patient_title_map(patient_ids)
    requester_names = _get_user_full_name_map(requester_ids)
    result_entered = _page_result_entered_map([row.get("name") for row in page_rows])
    return [
        {
            "lab_order": row.get("name"),
            "patient": patient_titles.get(row.get("patient")) or row.get("patient"),
            "owner": row.get("primary_owner"),
            "consultation": row.get("consultation"),
            "service_branch": row.get("service_branch"),
            "requested_by": requester_names.get(row.get("requested_by")) or row.get("requested_by"),
            "status": row.get("status"),
            "requested_on": row.get("requested_on"),
            "result_entered_on": result_entered.get(row.get("name")),
            "reviewed_on": row.get("doctor_reviewed_on"),
            "linked_invoice": row.get("linked_invoice"),
        }
        for row in page_rows
    ]


@frappe.whitelist()
@frappe.read_only()
def get_lab_order_report_view(
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

    if not frappe.db.exists("DocType", DOCTYPE):
        return {
            "title": _("Laboratory Report"),
            "columns": _columns(),
            "rows": [],
            "summary": [],
            "chart": None,
            "total": 0,
            "start": start,
            "page_length": page_length,
            "metadata": {"pagination_mode": "query-level", "detail_rows_materialized": False},
        }

    total = frappe.db.count(DOCTYPE, filters=query_filters)
    page_rows = frappe.get_all(
        DOCTYPE,
        filters=query_filters,
        fields=[
            "name",
            "patient",
            "primary_owner",
            "consultation",
            "service_branch",
            "requested_by",
            "status",
            "requested_on",
            "doctor_reviewed_on",
            "linked_invoice",
        ],
        order_by="requested_on desc, name desc",
        limit_start=start,
        limit_page_length=page_length,
    )
    summary, counts = _summary(query_filters, cint(total))
    return {
        "title": _("Laboratory Report"),
        "columns": _columns(),
        "rows": _render_rows(page_rows),
        "summary": summary,
        "chart": _chart(counts),
        "message": "",
        "total": cint(total),
        "start": start,
        "page_length": page_length,
        "metadata": {
            "pagination_mode": "query-level",
            "detail_rows_materialized": False,
            "summary_mode": "aggregate",
            "source": "lab-order-report",
        },
    }
