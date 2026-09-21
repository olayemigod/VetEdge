from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, cint, cstr, flt, getdate, nowdate

from vetedge.services.portal_access import require_internal_user
from vetedge.services.report_visibility import normalize_report_filters
from vetedge.services.reporting_structure import _date_filter_dict, _get_patient_title_map, _get_user_full_name_map, _vaccination_due_state


DOCTYPE = "Veterinary Vaccination Record"
PAGE_LENGTH_MAX = 100
SORT_FIELDS = {
    "vaccination_record": "name",
    "owner": "primary_owner",
    "vaccine": "vaccine",
    "service_branch": "service_branch",
    "administered_by": "administered_by",
    "administered_on": "administered_on",
    "next_due_date": "next_due_date",
    "status": "status",
    "linked_invoice": "linked_invoice",
}
DEFAULT_SORT = {"field": "administered_on", "direction": "desc"}


def _filters(value: str | dict | None) -> dict:
    if not value:
        value = {}
    parsed = value if isinstance(value, dict) else frappe.parse_json(value)
    if not isinstance(parsed, dict):
        frappe.throw(_("Expected report filters as a JSON object."), frappe.ValidationError)
    cleaned = {key: item for key, item in parsed.items() if item not in (None, "")}
    return dict(normalize_report_filters("Vaccination Report", cleaned) or {})


def _require_read_permission() -> None:
    if not frappe.has_permission(DOCTYPE, "read"):
        frappe.throw(_("You do not have permission to view vaccination records."), frappe.PermissionError)


def _base_query_filters(report_filters: dict) -> dict:
    filters = _date_filter_dict("administered_on", frappe._dict(report_filters), 30)
    if report_filters.get("branch"):
        filters["service_branch"] = report_filters.get("branch")
    if report_filters.get("status"):
        filters["status"] = report_filters.get("status")
    if report_filters.get("practitioner"):
        filters["administered_by"] = report_filters.get("practitioner")
    if report_filters.get("patient"):
        filters["patient"] = report_filters.get("patient")
    owner = report_filters.get("owner") or report_filters.get("customer")
    if owner:
        filters["primary_owner"] = owner
    if report_filters.get("vaccine"):
        filters["vaccine"] = report_filters.get("vaccine")
    return filters


def _with_due_filter(query_filters: dict, due_status: str | None) -> dict:
    due_status = cstr(due_status or "").strip()
    filters = dict(query_filters)
    if not due_status:
        return filters
    existing_status = cstr(filters.get("status") or "").strip()
    if existing_status and existing_status != "Administered":
        filters["name"] = "__vetedge_no_matching_vaccination__"
        return filters
    filters["status"] = "Administered"
    today = getdate(nowdate())
    if due_status == "Due Soon":
        filters["next_due_date"] = ("between", [today, add_days(today, 30)])
    elif due_status == "Overdue":
        filters["next_due_date"] = ("<", today)
    return filters


def _normalize_sort(value: str | dict | None) -> dict:
    if not value:
        return dict(DEFAULT_SORT)
    parsed = value if isinstance(value, dict) else frappe.parse_json(value)
    if not isinstance(parsed, dict):
        frappe.throw(_("Expected report sort as a JSON object."), frappe.ValidationError)
    field = cstr(parsed.get("field") or parsed.get("fieldname") or parsed.get("key")).strip()
    direction = cstr(parsed.get("direction") or parsed.get("order")).strip().lower()
    if field not in SORT_FIELDS or direction not in {"asc", "desc"}:
        return dict(DEFAULT_SORT)
    return {"field": field, "direction": direction}


def _order_by(sort: dict) -> str:
    field = sort.get("field") if sort.get("field") in SORT_FIELDS else DEFAULT_SORT["field"]
    direction = "asc" if sort.get("direction") == "asc" else "desc"
    source = SORT_FIELDS[field]
    if source == "name":
        return f"name {direction}"
    return f"{source} {direction}, name {direction}"


def _columns() -> list[dict]:
    columns = [
        {"fieldname": "vaccination_record", "label": _("Vaccination Record"), "fieldtype": "Link", "options": DOCTYPE},
        {"fieldname": "patient", "label": _("Patient"), "fieldtype": "Data"},
        {"fieldname": "owner", "label": _("Owner"), "fieldtype": "Link", "options": "Customer"},
        {"fieldname": "vaccine", "label": _("Vaccine"), "fieldtype": "Link", "options": "Veterinary Vaccine"},
        {"fieldname": "service_branch", "label": _("Service Branch"), "fieldtype": "Link", "options": "Branch"},
        {"fieldname": "administered_by", "label": _("Administered By"), "fieldtype": "Data"},
        {"fieldname": "administered_on", "label": _("Administered On"), "fieldtype": "Datetime"},
        {"fieldname": "next_due_date", "label": _("Next Due Date"), "fieldtype": "Date"},
        {"fieldname": "due_status", "label": _("Due Status"), "fieldtype": "Data"},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data"},
        {"fieldname": "linked_invoice", "label": _("Linked Invoice"), "fieldtype": "Link", "options": "Sales Invoice"},
    ]
    for column in columns:
        column["sortable"] = column.get("fieldname") in SORT_FIELDS
    return columns


def _count_for(base_filters: dict, extra: dict) -> int:
    filters = dict(base_filters)
    existing_status = cstr(filters.get("status") or "").strip()
    requested_status = cstr(extra.get("status") or "").strip()
    if existing_status and requested_status and existing_status != requested_status:
        return 0
    filters.update(extra)
    return cint(frappe.db.count(DOCTYPE, filters=filters))


def _summary(base_filters: dict, due_status: str, total: int) -> tuple[list[dict], int, int]:
    due_status = cstr(due_status or "").strip()
    today = getdate(nowdate())
    if due_status:
        administered = total if due_status in {"Administered", "Due Soon", "Overdue"} else 0
        due_soon = total if due_status == "Due Soon" else 0
        overdue = total if due_status == "Overdue" else 0
        cancelled = 0
    else:
        administered = _count_for(base_filters, {"status": "Administered"})
        due_soon = _count_for(
            base_filters,
            {"status": "Administered", "next_due_date": ("between", [today, add_days(today, 30)])},
        )
        overdue = _count_for(base_filters, {"status": "Administered", "next_due_date": ("<", today)})
        cancelled = _count_for(base_filters, {"status": "Cancelled"})
    cards = [
        {"label": _("Vaccination Records"), "value": total, "indicator": "Blue", "datatype": "Int"},
        {"label": _("Administered"), "value": administered, "indicator": "Green", "datatype": "Int"},
        {"label": _("Due Soon"), "value": due_soon, "indicator": "Orange", "datatype": "Int"},
        {"label": _("Overdue"), "value": overdue, "indicator": "Red", "datatype": "Int"},
        {"label": _("Cancelled"), "value": cancelled, "indicator": "Red", "datatype": "Int"},
        {
            "label": _("Compliance Rate"),
            "value": flt((administered / total) * 100, 1) if total else 0,
            "indicator": "Green",
            "datatype": "Percent",
        },
    ]
    return cards, due_soon, overdue


def _chart(due_soon: int, overdue: int) -> dict | None:
    if not due_soon and not overdue:
        return None
    return {
        "title": _("Vaccinations Due"),
        "type": "bar",
        "data": {
            "labels": [_("Due Soon"), _("Overdue")],
            "datasets": [{"name": _("Vaccinations"), "values": [due_soon, overdue]}],
        },
    }


def _render_rows(page_rows) -> list[dict]:
    patient_ids = {row.get("patient") for row in page_rows if row.get("patient")}
    practitioner_ids = {row.get("administered_by") for row in page_rows if row.get("administered_by")}
    patient_titles = _get_patient_title_map(patient_ids)
    practitioner_names = _get_user_full_name_map(practitioner_ids)
    return [
        {
            "vaccination_record": row.get("name"),
            "patient": patient_titles.get(row.get("patient")) or row.get("patient"),
            "owner": row.get("primary_owner"),
            "vaccine": row.get("vaccine"),
            "service_branch": row.get("service_branch"),
            "administered_by": practitioner_names.get(row.get("administered_by")) or row.get("administered_by"),
            "administered_on": row.get("administered_on"),
            "next_due_date": row.get("next_due_date"),
            "due_status": _vaccination_due_state(row.get("next_due_date"), row.get("status")),
            "status": row.get("status"),
            "linked_invoice": row.get("linked_invoice"),
        }
        for row in page_rows
    ]


@frappe.whitelist()
@frappe.read_only()
def get_vaccination_report_view(
    filters: str | dict | None = None,
    start: int = 0,
    page_length: int = 50,
    sort: str | dict | None = None,
) -> dict:
    require_internal_user()
    _require_read_permission()
    report_filters = _filters(filters)
    base_filters = _base_query_filters(report_filters)
    due_status = cstr(report_filters.get("due_status") or "").strip()
    query_filters = _with_due_filter(base_filters, due_status)
    normalized_sort = _normalize_sort(sort)
    start = max(cint(start), 0)
    page_length = min(max(cint(page_length) or 50, 1), PAGE_LENGTH_MAX)

    if not frappe.db.exists("DocType", DOCTYPE):
        return {
            "title": _("Vaccination Report"),
            "columns": _columns(),
            "rows": [],
            "summary": [],
            "chart": None,
            "total": 0,
            "start": start,
            "page_length": page_length,
            "sort": normalized_sort,
            "metadata": {"pagination_mode": "query-level", "sorting_mode": "server-allowlist", "detail_rows_materialized": False},
        }

    total = cint(frappe.db.count(DOCTYPE, filters=query_filters))
    page_rows = frappe.get_all(
        DOCTYPE,
        filters=query_filters,
        fields=[
            "name",
            "patient",
            "primary_owner",
            "vaccine",
            "service_branch",
            "administered_by",
            "administered_on",
            "next_due_date",
            "status",
            "linked_invoice",
        ],
        order_by=_order_by(normalized_sort),
        limit_start=start,
        limit_page_length=page_length,
    )
    summary, due_soon, overdue = _summary(base_filters, due_status, total)
    return {
        "title": _("Vaccination Report"),
        "columns": _columns(),
        "rows": _render_rows(page_rows),
        "summary": summary,
        "chart": _chart(due_soon, overdue),
        "message": "",
        "total": total,
        "start": start,
        "page_length": page_length,
        "sort": normalized_sort,
        "metadata": {
            "pagination_mode": "query-level",
            "sorting_mode": "server-allowlist",
            "detail_rows_materialized": False,
            "summary_mode": "aggregate",
            "due_filter_mode": "database",
            "source": "vaccination-report",
        },
    }
