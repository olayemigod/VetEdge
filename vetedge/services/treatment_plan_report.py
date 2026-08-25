from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from vetedge.services.portal_access import require_internal_user
from vetedge.services.reporting_logic_v3 import execute_structured_report

PAGE_LENGTH_MAX = 100


def _filters(value: str | dict | None) -> dict:
    if not value:
        return {}
    parsed = value if isinstance(value, dict) else frappe.parse_json(value)
    if not isinstance(parsed, dict):
        frappe.throw(_("Expected report filters as a JSON object."), frappe.ValidationError)
    return {key: item for key, item in parsed.items() if item not in (None, "")}


def _columns(columns) -> list[dict]:
    normalized = []
    for column in columns or []:
        if isinstance(column, dict):
            fieldname = column.get("fieldname") or column.get("key")
            if not fieldname:
                continue
            normalized.append(
                {
                    "fieldname": fieldname,
                    "label": column.get("label") or fieldname.replace("_", " ").title(),
                    "fieldtype": column.get("fieldtype") or column.get("type") or "Data",
                }
            )
        elif isinstance(column, str):
            fieldname = column.split(":", 1)[0]
            normalized.append({"fieldname": fieldname, "label": fieldname.replace("_", " ").title(), "fieldtype": "Data"})
    return normalized


@frappe.whitelist()
def get_planned_treatment_view(
    filters: str | dict | None = None,
    start: int = 0,
    page_length: int = 50,
) -> dict:
    require_internal_user()
    report_filters = _filters(filters)
    columns, rows, message, _chart, summary = execute_structured_report("Planned Treatment", report_filters)
    start = max(cint(start), 0)
    page_length = min(max(cint(page_length) or 50, 1), PAGE_LENGTH_MAX)
    rows = list(rows or [])
    total = len(rows)
    return {
        "title": _("Planned Treatment"),
        "subtitle": _("Treatment plans are clinical reports derived from consultations; they are not standalone clinical service records."),
        "columns": _columns(columns),
        "rows": rows[start : start + page_length],
        "summary": summary or [],
        "message": message or "",
        "start": start,
        "page_length": page_length,
        "total": total,
    }
