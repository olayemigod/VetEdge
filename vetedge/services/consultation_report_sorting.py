from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services import consultation_report as base
from vetedge.services.portal_access import require_internal_user


SORT_FIELDS = {
    "consultation": "c.`name`",
    "consultation_datetime": "c.`consultation_datetime`",
    "service_branch": "c.`service_branch`",
    "owner": "c.`primary_owner`",
    "practitioner": "c.`consulting_practitioner`",
    "consultation_type": "c.`consultation_type`",
    "linked_appointment": "c.`linked_appointment`",
    "status": "c.`status`",
    "payment_status": "c.`payment_status`",
    "follow_up_date": "c.`follow_up_date`",
    "next_appointment": "c.`follow_up_appointment`",
    "created_by": "c.`owner`",
}
DEFAULT_SORT = {"field": "consultation_datetime", "direction": "desc"}
UNSAFE_SORT_FIELDS = {
    "patient",
    "invoice",
    "invoice_status",
    "planned_treatment_total",
    "vaccination_count",
    "has_vaccination",
    "outcome_assessment_summary",
}


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


def _columns() -> list[dict]:
    columns = []
    for column in base._columns():
        item = dict(column)
        fieldname = cstr(item.get("fieldname"))
        item["sortable"] = fieldname in SORT_FIELDS and fieldname not in UNSAFE_SORT_FIELDS
        columns.append(item)
    return columns


def _order_by(sort: dict) -> str:
    field = sort.get("field") if sort.get("field") in SORT_FIELDS else DEFAULT_SORT["field"]
    direction = "ASC" if sort.get("direction") == "asc" else "DESC"
    primary = SORT_FIELDS[field]
    if field == "consultation":
        return f"{primary} {direction}"
    return f"{primary} {direction}, c.`name` {direction}"


def _page_rows(where_sql: str, params: dict, start: int, page_length: int, sort: dict):
    page_params = dict(params)
    page_params["limit"] = page_length
    page_params["offset"] = start
    order_by = _order_by(sort)
    return frappe.db.sql(
        f"""
        SELECT
            c.`name`, c.`consultation_datetime`, c.`service_branch`, c.`patient`, c.`primary_owner`,
            c.`consulting_practitioner`, c.`consulting_practitioner_name`, c.`consultation_type`,
            c.`linked_appointment`, c.`status`, c.`linked_invoice`, c.`payment_status`,
            c.`follow_up_date`, c.`follow_up_appointment`, c.`assessment_notes`, c.`owner`
        FROM `tabVeterinary Consultation` c
        WHERE {where_sql}
        ORDER BY {order_by}
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        page_params,
        as_dict=True,
    )


@frappe.whitelist()
@frappe.read_only()
def get_consultation_register_view(
    filters: str | dict | None = None,
    start: int = 0,
    page_length: int = 50,
    sort: str | dict | None = None,
) -> dict:
    require_internal_user()
    base._require_read_permission()
    report_filters = base._filters(filters)
    query_filters = base._query_filters(report_filters)
    where_sql, params = base._where_clause(query_filters, report_filters)
    normalized_sort = _normalize_sort(sort)
    start = max(cint(start), 0)
    page_length = min(max(cint(page_length) or 50, 1), base.PAGE_LENGTH_MAX)

    if not frappe.db.exists("DocType", base.DOCTYPE):
        return {
            "title": _("Consultation Register"),
            "columns": _columns(),
            "rows": [],
            "summary": [],
            "chart": None,
            "total": 0,
            "start": start,
            "page_length": page_length,
            "sort": normalized_sort,
            "metadata": {
                "pagination_mode": "query-level",
                "sorting_mode": "server-allowlist",
                "detail_rows_materialized": False,
            },
        }

    total = base._count_rows(where_sql, params)
    page_rows = _page_rows(where_sql, params, start, page_length, normalized_sort)
    return {
        "title": _("Consultation Register"),
        "columns": _columns(),
        "rows": base._render_rows(page_rows),
        "summary": base._summary(query_filters, report_filters, where_sql, params, total),
        "chart": base._chart(where_sql, params),
        "message": "",
        "total": total,
        "start": start,
        "page_length": page_length,
        "sort": normalized_sort,
        "metadata": {
            "pagination_mode": "query-level",
            "sorting_mode": "server-allowlist",
            "detail_rows_materialized": False,
            "enrichment_mode": "page-only",
            "summary_mode": "database-aggregate",
            "has_vaccination_filter_mode": "exists-subquery",
            "source": "consultation-register",
        },
    }
