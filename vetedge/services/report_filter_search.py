from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services.permissions import (
    get_vaccination_staff_users,
    get_veterinary_doctor_users,
)
from vetedge.services.portal_access import require_internal_user
from vetedge.services.report_visibility import normalize_report_filters, validate_report_access
from vetedge.services.reporting_catalog import require_reporting_entitlement

MAX_PAGE_LENGTH = 20

REPORT_FIELDS = {
    "Consultation Register": {"branch", "patient", "customer", "practitioner", "consultation_type"},
    "Planned Treatment": {"branch", "patient", "customer", "practitioner", "consultation_type", "item"},
    "Lab Order Report": {"branch", "patient", "customer", "practitioner"},
    "Vaccination Report": {"branch", "patient", "customer", "practitioner", "vaccine"},
    "Patient Register": {"branch", "customer", "species", "breed"},
    "Owner Register": {"branch", "customer"},
    "Service Revenue Breakdown": {"branch", "practitioner", "item"},
}

MASTER_FIELDS = {
    "consultation_type": ("Consultation Type", {"disabled": 0}),
    "item": ("Item", {"disabled": 0}),
    "vaccine": ("Veterinary Vaccine", {"disabled": 0}),
    "species": ("Veterinary Species", {"disabled": 0}),
    "breed": ("Veterinary Breed", {"disabled": 0}),
}


def _clean_filters(filters) -> dict:
    if not filters:
        return {}
    value = frappe.parse_json(filters) if isinstance(filters, str) else filters
    if not isinstance(value, dict):
        frappe.throw(_("Expected report filters as a JSON object."), frappe.ValidationError)
    return {key: item for key, item in value.items() if item not in (None, "")}


def _option(value, label=None) -> dict:
    value = cstr(value or "").strip()
    return {"value": value, "label": cstr(label or value).strip() or value}


def _bounded(value: int | str | None, default: int = MAX_PAGE_LENGTH) -> int:
    return min(max(cint(value) or default, 1), MAX_PAGE_LENGTH)


def _search_branch(txt: str, start: int, page_length: int, normalized: dict) -> list[dict]:
    branch = cstr(normalized.get("branch") or "").strip()
    filters = {}
    if branch:
        filters["name"] = branch
        if txt and txt.lower() not in branch.lower():
            return []
    elif txt:
        filters["name"] = ["like", f"%{txt}%"]

    if not frappe.has_permission("Branch", "read"):
        return []
    rows = frappe.get_list(
        "Branch",
        fields=["name"],
        filters=filters,
        order_by="name asc",
        start=start,
        page_length=page_length,
    )
    return [_option(row.name) for row in rows]


def _search_patient(txt: str, start: int, page_length: int, normalized: dict) -> list[dict]:
    if not frappe.has_permission("Veterinary Patient", "read"):
        return []
    filters = {"status": ["!=", "Deceased"]}
    branch = cstr(normalized.get("branch") or "").strip()
    if branch:
        filters["default_branch"] = branch
    or_filters = []
    if txt:
        pattern = f"%{txt}%"
        or_filters = [["Veterinary Patient", "name", "like", pattern], ["Veterinary Patient", "patient_name", "like", pattern]]
    rows = frappe.get_list(
        "Veterinary Patient",
        fields=["name", "patient_name"],
        filters=filters,
        or_filters=or_filters,
        order_by="patient_name asc, name asc",
        start=start,
        page_length=page_length,
    )
    return [_option(row.name, row.patient_name or row.name) for row in rows]


def _search_customer(txt: str, start: int, page_length: int, normalized: dict) -> list[dict]:
    if not frappe.has_permission("Customer", "read"):
        return []
    branch = cstr(normalized.get("branch") or "").strip()
    if not branch:
        filters = {}
        or_filters = []
        if txt:
            pattern = f"%{txt}%"
            or_filters = [["Customer", "name", "like", pattern], ["Customer", "customer_name", "like", pattern]]
        rows = frappe.get_list(
            "Customer",
            fields=["name", "customer_name"],
            filters=filters,
            or_filters=or_filters,
            order_by="customer_name asc, name asc",
            start=start,
            page_length=page_length,
        )
        return [_option(row.name, row.customer_name or row.name) for row in rows]

    search = f"%{txt}%"
    rows = frappe.db.sql(
        """
        SELECT DISTINCT c.name, c.customer_name
        FROM `tabCustomer` c
        INNER JOIN `tabVeterinary Patient` p ON p.primary_owner = c.name
        WHERE p.default_branch = %(branch)s
          AND (%(txt)s = '' OR c.name LIKE %(search)s OR c.customer_name LIKE %(search)s)
        ORDER BY COALESCE(NULLIF(c.customer_name, ''), c.name) ASC, c.name ASC
        LIMIT %(start)s, %(page_length)s
        """,
        {"branch": branch, "txt": txt, "search": search, "start": start, "page_length": page_length},
        as_dict=True,
    )
    return [_option(row.name, row.customer_name or row.name) for row in rows]


def _branch_allowed_users(users: list[list | tuple], branch: str) -> list[list | tuple]:
    if not branch or not users or not frappe.db.exists("DocType", "Branch User Assignment"):
        return users
    candidate_names = [cstr(row[0]).strip() for row in users if row and cstr(row[0]).strip()]
    if not candidate_names:
        return []
    assigned = set(
        frappe.get_all(
            "Branch User Assignment",
            filters={"user": ["in", candidate_names], "branch": branch, "disabled": ["!=", 1]},
            pluck="user",
        )
    )
    return [row for row in users if cstr(row[0]).strip() in assigned]


def _search_practitioner(report_name: str, txt: str, start: int, page_length: int, normalized: dict) -> list[dict]:
    searcher = get_vaccination_staff_users if report_name == "Vaccination Report" else get_veterinary_doctor_users
    # Ask for a slightly wider bounded candidate window so branch filtering does
    # not routinely leave a nearly-empty 20-row chooser. No unbounded User load.
    candidate_limit = min(MAX_PAGE_LENGTH * 3, 60)
    rows = searcher("User", txt, "name", 0, candidate_limit, {}) or []
    rows = _branch_allowed_users(rows, cstr(normalized.get("branch") or "").strip())
    rows = rows[start : start + page_length]
    return [_option(row[0], row[1] if len(row) > 1 else row[0]) for row in rows]


def _search_master(field: str, txt: str, start: int, page_length: int) -> list[dict]:
    doctype, base_filters = MASTER_FIELDS[field]
    if not frappe.has_permission(doctype, "read"):
        return []
    filters = dict(base_filters)
    if txt:
        filters["name"] = ["like", f"%{txt}%"]
    rows = frappe.get_list(
        doctype,
        fields=["name"],
        filters=filters,
        order_by="name asc",
        start=start,
        page_length=page_length,
    )
    return [_option(row.name) for row in rows]


@frappe.whitelist()
@frappe.read_only()
def search_report_filter_options(
    report_name: str,
    field: str,
    txt: str = "",
    start: int = 0,
    page_length: int = MAX_PAGE_LENGTH,
    filters=None,
) -> list[dict]:
    require_internal_user()
    report_name = cstr(report_name or "").strip()
    field = cstr(field or "").strip()
    if field not in REPORT_FIELDS.get(report_name, set()):
        frappe.throw(_("This filter is not available for the selected report."), frappe.PermissionError)

    validate_report_access(report_name)
    require_reporting_entitlement(report_name, scope_type="report")
    normalized = dict(normalize_report_filters(report_name, _clean_filters(filters)) or {})
    txt = cstr(txt or "").strip()
    start = max(cint(start), 0)
    page_length = _bounded(page_length)

    if field == "branch":
        return _search_branch(txt, start, page_length, normalized)
    if field == "patient":
        return _search_patient(txt, start, page_length, normalized)
    if field == "customer":
        return _search_customer(txt, start, page_length, normalized)
    if field == "practitioner":
        return _search_practitioner(report_name, txt, start, page_length, normalized)
    if field in MASTER_FIELDS:
        return _search_master(field, txt, start, page_length)
    return []
