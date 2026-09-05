from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services.outbreak_permissions import normalize_outbreak_report_filters
from vetedge.services.permissions import (
    get_assigned_branches,
    get_current_user,
    user_has_global_branch_access,
)

DOCTYPE = "Veterinary Disease Outbreak"
DEFAULT_PAGE_LENGTH = 25
MAX_PAGE_LENGTH = 100

LIST_FIELDS = [
    "name",
    "outbreak_status",
    "service_branch",
    "company",
    "disease",
    "nadis_disease",
    "serotype",
    "outbreak_type",
    "number_new_outbreaks",
    "total_outbreaks",
    "date_outbreak_started",
    "date_investigated",
    "date_final_diagnosis",
    "modified",
]


def _clean_filters(filters) -> dict:
    if not filters:
        return {}
    value = frappe.parse_json(filters) if isinstance(filters, str) else filters
    if not isinstance(value, dict):
        frappe.throw(_("Expected Disease Outbreak filters as a JSON object."), frappe.ValidationError)
    return {key: item for key, item in value.items() if item not in (None, "")}


def _require_register_access() -> None:
    # Reuse the same fail-closed role/Branch policy as official NADIS outbreak reporting.
    # The normalized Branch returned here is deliberately ignored so an unfiltered
    # register can still show all branches the user is actually assigned to.
    normalize_outbreak_report_filters({})
    if not frappe.has_permission(DOCTYPE, "read"):
        frappe.throw(_("You are not permitted to read the Disease Outbreak Register."), frappe.PermissionError)


def _bounded_page_length(value) -> int:
    return min(max(cint(value) or DEFAULT_PAGE_LENGTH, 1), MAX_PAGE_LENGTH)


def _query_filters(filters: dict) -> tuple[dict, list]:
    result: dict = {}
    branch = cstr(filters.get("branch") or "").strip()
    if branch:
        normalized = normalize_outbreak_report_filters({"branch": branch})
        result["service_branch"] = normalized.get("branch")

    for source, target in (
        ("company", "company"),
        ("status", "outbreak_status"),
        ("disease", "disease"),
    ):
        value = cstr(filters.get(source) or "").strip()
        if value:
            result[target] = value

    from_date = cstr(filters.get("from_date") or "").strip()
    to_date = cstr(filters.get("to_date") or "").strip()
    if from_date and to_date:
        result["date_investigated"] = ["between", [from_date, to_date]]
    elif from_date:
        result["date_investigated"] = [">=", from_date]
    elif to_date:
        result["date_investigated"] = ["<=", to_date]

    txt = cstr(filters.get("txt") or "").strip()
    or_filters = []
    if txt:
        pattern = f"%{txt}%"
        or_filters = [
            [DOCTYPE, "name", "like", pattern],
            [DOCTYPE, "disease", "like", pattern],
            [DOCTYPE, "nadis_disease", "like", pattern],
            [DOCTYPE, "serotype", "like", pattern],
        ]
    return result, or_filters


def _count_rows(filters: dict, or_filters: list) -> int:
    rows = frappe.get_list(
        DOCTYPE,
        fields=[{"COUNT": "*", "as": "total"}],
        filters=filters,
        or_filters=or_filters or None,
        limit_page_length=1,
    )
    return cint(rows[0].get("total") if rows else 0)


@frappe.whitelist()
@frappe.read_only()
def get_outbreak_register(filters=None, start: int = 0, page_length: int = DEFAULT_PAGE_LENGTH) -> dict:
    _require_register_access()
    cleaned = _clean_filters(filters)
    query_filters, or_filters = _query_filters(cleaned)
    start = max(cint(start), 0)
    page_length = _bounded_page_length(page_length)

    rows = frappe.get_list(
        DOCTYPE,
        fields=LIST_FIELDS,
        filters=query_filters,
        or_filters=or_filters or None,
        order_by="date_investigated desc, modified desc, name desc",
        start=start,
        page_length=page_length,
    )
    total = _count_rows(query_filters, or_filters)

    return {
        "rows": rows,
        "total": total,
        "start": start,
        "page_length": page_length,
        "can_create": bool(frappe.has_permission(DOCTYPE, "create")),
        "can_write": bool(frappe.has_permission(DOCTYPE, "write")),
    }


@frappe.whitelist()
@frappe.read_only()
def search_outbreak_branches(txt: str = "", start: int = 0, page_length: int = 20) -> list[dict]:
    _require_register_access()
    if not frappe.has_permission("Branch", "read"):
        return []

    user = get_current_user()
    txt = cstr(txt or "").strip()
    start = max(cint(start), 0)
    page_length = min(max(cint(page_length) or 20, 1), 20)

    filters = []
    if not user_has_global_branch_access(user):
        assigned = sorted({cstr(branch).strip() for branch in get_assigned_branches(user) if cstr(branch).strip()})
        if not assigned:
            return []
        filters.append(["Branch", "name", "in", assigned])
    if txt:
        filters.append(["Branch", "name", "like", f"%{txt}%"])

    rows = frappe.get_list(
        "Branch",
        fields=["name"],
        filters=filters,
        order_by="name asc",
        start=start,
        page_length=page_length,
    )
    return [{"value": row.get("name"), "label": row.get("name")} for row in rows]
