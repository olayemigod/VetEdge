from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services.permissions import (
    ROLE_SYSTEM_MANAGER,
    ROLE_VETEDGE_ADMINISTRATOR,
    get_assigned_branches,
    get_vaccination_staff_users,
    get_veterinary_doctor_users,
    user_has_global_branch_access,
)
from vetedge.services.portal_access import require_internal_user
from vetedge.services.report_visibility import normalize_report_filters, validate_report_access
from vetedge.services.reporting_catalog import require_reporting_entitlement

MAX_PAGE_LENGTH = 20
CANDIDATE_WINDOW = 60

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


def _search_branch(txt: str, start: int, page_length: int) -> list[dict]:
    if not frappe.has_permission("Branch", "read"):
        return []

    user = frappe.session.user
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
    return [_option(row.name) for row in rows]


def _search_patient(txt: str, start: int, page_length: int, normalized: dict) -> list[dict]:
    if not frappe.has_permission("Veterinary Patient", "read"):
        return []
    filters = {"status": ["!=", "Deceased"]}
    branch = cstr(normalized.get("branch") or "").strip()
    if branch:
        filters["default_branch"] = branch
    owner = cstr(normalized.get("customer") or normalized.get("owner") or "").strip()
    if owner:
        filters["primary_owner"] = owner
    or_filters = []
    if txt:
        pattern = f"%{txt}%"
        or_filters = [
            ["Veterinary Patient", "name", "like", pattern],
            ["Veterinary Patient", "patient_name", "like", pattern],
        ]
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


def _customer_candidates(txt: str, limit: int) -> list[dict]:
    or_filters = []
    if txt:
        pattern = f"%{txt}%"
        or_filters = [
            ["Customer", "name", "like", pattern],
            ["Customer", "customer_name", "like", pattern],
        ]
    return frappe.get_list(
        "Customer",
        fields=["name", "customer_name"],
        or_filters=or_filters,
        order_by="customer_name asc, name asc",
        page_length=limit,
    )


def _search_customer(txt: str, start: int, page_length: int, normalized: dict) -> list[dict]:
    if not frappe.has_permission("Customer", "read"):
        return []

    patient = cstr(normalized.get("patient") or "").strip()
    if patient:
        patient_rows = frappe.get_list(
            "Veterinary Patient",
            fields=["primary_owner"],
            filters={"name": patient},
            page_length=1,
        )
        owner = cstr(patient_rows[0].get("primary_owner") if patient_rows else "").strip()
        if not owner:
            return []
        rows = frappe.get_list(
            "Customer",
            fields=["name", "customer_name"],
            filters={"name": owner},
            page_length=1,
        )
        if not rows:
            return []
        row = rows[0]
        label = row.get("customer_name") or row.get("name")
        if txt and txt.lower() not in f"{row.get('name')} {label}".lower():
            return []
        return [_option(row.get("name"), label)]

    branch = cstr(normalized.get("branch") or "").strip()
    candidate_limit = min(max(page_length * 3, page_length), CANDIDATE_WINDOW)
    candidates = _customer_candidates(txt, candidate_limit)
    if not branch:
        return [
            _option(row.get("name"), row.get("customer_name") or row.get("name"))
            for row in candidates[start : start + page_length]
        ]

    names = [row.get("name") for row in candidates if row.get("name")]
    if not names:
        return []
    visible_owners = set(
        frappe.get_list(
            "Veterinary Patient",
            fields=["primary_owner"],
            filters={"default_branch": branch, "primary_owner": ["in", names]},
            group_by="primary_owner",
            page_length=candidate_limit,
            pluck="primary_owner",
        )
    )
    filtered = [row for row in candidates if row.get("name") in visible_owners]
    return [
        _option(row.get("name"), row.get("customer_name") or row.get("name"))
        for row in filtered[start : start + page_length]
    ]


def _branch_allowed_users(users: list[list | tuple], branch: str) -> list[list | tuple]:
    if not branch or not users or not frappe.db.exists("DocType", "Branch User Assignment"):
        return users
    candidate_names = [cstr(row[0]).strip() for row in users if row and cstr(row[0]).strip()]
    if not candidate_names:
        return []

    assignment_filters = {"user": ["in", candidate_names], "branch": branch}
    assignment_meta = frappe.get_meta("Branch User Assignment")
    if assignment_meta.has_field("disabled"):
        assignment_filters["disabled"] = ["!=", 1]
    assigned = set(frappe.get_all("Branch User Assignment", filters=assignment_filters, pluck="user"))

    global_staff = set(
        frappe.get_all(
            "Has Role",
            filters={
                "parent": ["in", candidate_names],
                "parenttype": "User",
                "role": ["in", [ROLE_SYSTEM_MANAGER, ROLE_VETEDGE_ADMINISTRATOR]],
            },
            pluck="parent",
        )
    )
    allowed = assigned | global_staff
    return [row for row in users if cstr(row[0]).strip() in allowed]


def _search_practitioner(report_name: str, txt: str, start: int, page_length: int, normalized: dict) -> list[dict]:
    searcher = get_vaccination_staff_users if report_name == "Vaccination Report" else get_veterinary_doctor_users
    candidate_limit = min(MAX_PAGE_LENGTH * 3, CANDIDATE_WINDOW)
    rows = searcher("User", txt, "name", 0, candidate_limit, {}) or []
    rows = _branch_allowed_users(rows, cstr(normalized.get("branch") or "").strip())
    rows = rows[start : start + page_length]
    return [_option(row[0], row[1] if len(row) > 1 else row[0]) for row in rows]


def _search_master(field: str, txt: str, start: int, page_length: int, normalized: dict) -> list[dict]:
    doctype, requested_filters = MASTER_FIELDS[field]
    if not frappe.has_permission(doctype, "read"):
        return []
    meta = frappe.get_meta(doctype)
    filters = {key: value for key, value in requested_filters.items() if meta.has_field(key)}
    if field == "breed" and normalized.get("species") and meta.has_field("species"):
        filters["species"] = normalized.get("species")
    if txt:
        if field == "breed" and meta.has_field("breed_name"):
            pattern = f"%{txt}%"
            rows = frappe.get_list(
                doctype,
                fields=["name", "breed_name"],
                filters=filters,
                or_filters=[[doctype, "name", "like", pattern], [doctype, "breed_name", "like", pattern]],
                order_by="breed_name asc, name asc",
                start=start,
                page_length=page_length,
            )
            return [_option(row.name, row.breed_name or row.name) for row in rows]
        filters["name"] = ["like", f"%{txt}%"]
    fields = ["name"]
    if field == "breed" and meta.has_field("breed_name"):
        fields.append("breed_name")
    rows = frappe.get_list(
        doctype,
        fields=fields,
        filters=filters,
        order_by="name asc",
        start=start,
        page_length=page_length,
    )
    return [_option(row.name, row.get("breed_name") or row.name) for row in rows]


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
        return _search_branch(txt, start, page_length)
    if field == "patient":
        return _search_patient(txt, start, page_length, normalized)
    if field == "customer":
        return _search_customer(txt, start, page_length, normalized)
    if field == "practitioner":
        return _search_practitioner(report_name, txt, start, page_length, normalized)
    if field in MASTER_FIELDS:
        return _search_master(field, txt, start, page_length, normalized)
    return []
