from __future__ import annotations

from typing import Any

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
FILTER_FIELDS = {
    "consultation_datetime",
    "service_branch",
    "consulting_practitioner",
    "status",
    "patient",
    "primary_owner",
    "consultation_type",
    "payment_status",
    "owner",
}


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


def _sql_condition(field: str, value: Any, params: dict, index: int) -> str:
    if field not in FILTER_FIELDS:
        return ""
    column = f"c.`{field}`"
    key = f"p_{index}"
    if isinstance(value, (list, tuple)) and value:
        operator = cstr(value[0]).strip().lower()
        operand = value[1] if len(value) > 1 else None
        if operator == "between" and isinstance(operand, (list, tuple)) and len(operand) >= 2:
            params[f"{key}_from"] = operand[0]
            params[f"{key}_to"] = operand[1]
            return f"{column} BETWEEN %({key}_from)s AND %({key}_to)s"
        if operator in {">=", "<=", ">", "<", "!=", "="}:
            params[key] = operand
            return f"{column} {operator} %({key})s"
        if operator in {"in", "not in"} and isinstance(operand, (list, tuple, set)):
            values = list(operand)
            if not values:
                return "1=0" if operator == "in" else "1=1"
            placeholders = []
            for value_index, item in enumerate(values):
                item_key = f"{key}_{value_index}"
                params[item_key] = item
                placeholders.append(f"%({item_key})s")
            return f"{column} {'IN' if operator == 'in' else 'NOT IN'} ({', '.join(placeholders)})"
        if operator == "is":
            token = cstr(operand).strip().lower()
            if token in {"set", "not null"}:
                return f"{column} IS NOT NULL AND {column} != ''"
            if token in {"not set", "null"}:
                return f"({column} IS NULL OR {column} = '')"
    params[key] = value
    return f"{column} = %({key})s"


def _where_clause(query_filters: dict, report_filters: dict) -> tuple[str, dict]:
    params: dict = {}
    conditions = []
    for index, (field, value) in enumerate(query_filters.items()):
        condition = _sql_condition(field, value, params, index)
        if condition:
            conditions.append(condition)

    follow_up = report_filters.get("has_follow_up")
    if follow_up in (1, "1", "Yes"):
        conditions.append("((c.`follow_up_date` IS NOT NULL AND c.`follow_up_date` != '') OR (c.`follow_up_appointment` IS NOT NULL AND c.`follow_up_appointment` != ''))")
    elif follow_up in (0, "0", "No"):
        conditions.append("((c.`follow_up_date` IS NULL OR c.`follow_up_date` = '') AND (c.`follow_up_appointment` IS NULL OR c.`follow_up_appointment` = ''))")

    has_vaccination = report_filters.get("has_vaccination")
    if has_vaccination in (1, "1", "Yes", 0, "0", "No"):
        wants = has_vaccination in (1, "1", "Yes")
        exists_sql = "EXISTS (SELECT 1 FROM `tabVeterinary Vaccination Record` v WHERE v.`linked_consultation` = c.`name` LIMIT 1)"
        conditions.append(exists_sql if wants else f"NOT {exists_sql}")

    return (" AND ".join(conditions) if conditions else "1=1"), params


def _page_rows(where_sql: str, params: dict, start: int, page_length: int):
    page_params = dict(params)
    page_params["limit"] = page_length
    page_params["offset"] = start
    return frappe.db.sql(
        f"""
        SELECT
            c.`name`, c.`consultation_datetime`, c.`service_branch`, c.`patient`, c.`primary_owner`,
            c.`consulting_practitioner`, c.`consulting_practitioner_name`, c.`consultation_type`,
            c.`linked_appointment`, c.`status`, c.`linked_invoice`, c.`payment_status`,
            c.`follow_up_date`, c.`follow_up_appointment`, c.`assessment_notes`, c.`owner`
        FROM `tabVeterinary Consultation` c
        WHERE {where_sql}
        ORDER BY c.`consultation_datetime` DESC, c.`name` DESC
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        page_params,
        as_dict=True,
    )


def _count_rows(where_sql: str, params: dict) -> int:
    rows = frappe.db.sql(
        f"SELECT COUNT(*) AS `row_count` FROM `tabVeterinary Consultation` c WHERE {where_sql}",
        params,
        as_dict=True,
    )
    return cint(rows[0].get("row_count")) if rows else 0


def _status_counts(where_sql: str, params: dict) -> dict[str, int]:
    rows = frappe.db.sql(
        f"SELECT c.`status`, COUNT(*) AS `row_count` FROM `tabVeterinary Consultation` c WHERE {where_sql} GROUP BY c.`status`",
        params,
        as_dict=True,
    )
    return {cstr(row.get("status")): cint(row.get("row_count")) for row in rows}


def _planned_total(where_sql: str, params: dict) -> float:
    if not frappe.db.exists("DocType", "Planned Treatment Item"):
        return 0.0
    rows = frappe.db.sql(
        f"""
        SELECT SUM(CASE WHEN IFNULL(pt.`amount`, 0) != 0 THEN pt.`amount` ELSE IFNULL(pt.`qty`, 0) * IFNULL(pt.`rate`, 0) END) AS `planned_total`
        FROM `tabPlanned Treatment Item` pt
        INNER JOIN `tabVeterinary Consultation` c ON c.`name` = pt.`parent`
        WHERE pt.`parenttype` = 'Veterinary Consultation' AND {where_sql}
        """,
        params,
        as_dict=True,
    )
    return flt(rows[0].get("planned_total")) if rows else 0.0


def _follow_up_count(query_filters: dict, report_filters: dict, total: int) -> int:
    selected = report_filters.get("has_follow_up")
    if selected in (1, "1", "Yes"):
        return total
    if selected in (0, "0", "No"):
        return 0
    summary_filters = dict(report_filters)
    summary_filters["has_follow_up"] = "Yes"
    where_sql, params = _where_clause(query_filters, summary_filters)
    return _count_rows(where_sql, params)


def _summary(query_filters: dict, report_filters: dict, where_sql: str, params: dict, total: int) -> list[dict]:
    counts = _status_counts(where_sql, params)
    completed = sum(counts.get(status, 0) for status in COMPLETED_STATUSES)
    active = sum(counts.get(status, 0) for status in ACTIVE_STATUSES)
    cancelled = sum(counts.get(status, 0) for status in CANCELLED_STATUSES)
    awaiting_payment = counts.get("Awaiting Payment", 0)
    planned_total = _planned_total(where_sql, params)
    return [
        {"label": _("Total Consultations"), "value": total, "indicator": "Blue", "datatype": "Int"},
        {"label": _("Completed"), "value": completed, "indicator": "Green", "datatype": "Int"},
        {"label": _("Active / In Progress"), "value": active, "indicator": "Orange", "datatype": "Int"},
        {"label": _("Awaiting Payment"), "value": awaiting_payment, "indicator": "Orange", "datatype": "Int"},
        {"label": _("Cancelled"), "value": cancelled, "indicator": "Red", "datatype": "Int"},
        {"label": _("Completion Rate"), "value": flt((completed / total) * 100, 1) if total else 0, "indicator": "Green", "datatype": "Percent"},
        {"label": _("Average Planned Value"), "value": flt(planned_total / total, 2) if total else 0, "indicator": "Blue", "datatype": "Currency"},
        {"label": _("Follow-up Required"), "value": _follow_up_count(query_filters, report_filters, total), "indicator": "Purple", "datatype": "Int"},
    ]


def _chart(where_sql: str, params: dict) -> dict | None:
    counts = _status_counts(where_sql, params)
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
    query_filters = _query_filters(report_filters)
    where_sql, params = _where_clause(query_filters, report_filters)
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

    total = _count_rows(where_sql, params)
    page_rows = _page_rows(where_sql, params, start, page_length)
    return {
        "title": _("Consultation Register"),
        "columns": _columns(),
        "rows": _render_rows(page_rows),
        "summary": _summary(query_filters, report_filters, where_sql, params, total),
        "chart": _chart(where_sql, params),
        "message": "",
        "total": total,
        "start": start,
        "page_length": page_length,
        "metadata": {
            "pagination_mode": "query-level",
            "detail_rows_materialized": False,
            "enrichment_mode": "page-only",
            "summary_mode": "database-aggregate",
            "has_vaccination_filter_mode": "exists-subquery",
            "source": "consultation-register",
        },
    }
