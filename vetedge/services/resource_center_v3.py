from __future__ import annotations

import frappe
from frappe.utils import cint

from vetedge.coreedge_adapter import get_current_vetedge_branch
from vetedge.services import resource_center as legacy
from vetedge.services import resource_center_v2 as v2
from vetedge.services.display_labels import enrich_link_display_values


CLINICAL_LIST_CONFIG = {
    "lab-orders": {
        "fields": ["name", "patient", "status", "service_branch", "requested_on", "requested_by", "linked_invoice", "modified"],
        "date_field": "requested_on",
    },
    "vaccinations": {
        "fields": ["name", "patient", "status", "service_branch", "vaccine", "administered_on", "next_due_date", "linked_invoice", "modified"],
        "date_field": "administered_on",
    },
}


def _context_branch() -> str:
    try:
        branch = str(get_current_vetedge_branch() or "").strip()
    except Exception:
        branch = ""
    return "" if branch.lower() in {"all", "all branches"} else branch


def _columns(meta, fields: list[str]) -> list[dict]:
    columns = []
    for fieldname in fields:
        if fieldname == "name":
            columns.append({"fieldname": "name", "label": "ID", "fieldtype": "Data"})
            continue
        if fieldname == "modified":
            columns.append({"fieldname": "modified", "label": "Modified", "fieldtype": "Datetime"})
            continue
        field = meta.get_field(fieldname)
        if not field:
            continue
        columns.append(
            {
                "fieldname": fieldname,
                "label": field.label or fieldname.replace("_", " ").title(),
                "fieldtype": field.fieldtype,
                "options": field.options or "",
            }
        )
    return columns


def _hydrate_link_column_options(state: dict) -> dict:
    """Ensure generic Resource Center columns carry Link targets for display-label enrichment."""
    doctype = str(state.get("doctype") or "").strip()
    if not doctype:
        return state
    meta = frappe.get_meta(doctype)
    for column in state.get("columns") or []:
        if column.get("fieldtype") != "Link" or column.get("options"):
            continue
        field = meta.get_field(column.get("fieldname"))
        if field and field.fieldtype == "Link":
            column["options"] = field.options or ""
    return state


def _clinical_page(
    resource: str,
    search: str,
    start: int,
    page_length: int,
    patient: str,
    service_branch: str,
    status: str,
    from_date: str,
    to_date: str,
    vaccine: str,
    lab_test: str,
) -> dict:
    legacy._require_login()
    resource_config = legacy._resource(resource)
    doctype = resource_config["doctype"]
    if not frappe.has_permission(doctype, "read"):
        frappe.throw("You are not permitted to view this clinical resource.", frappe.PermissionError)
    config = CLINICAL_LIST_CONFIG[resource]
    meta = frappe.get_meta(doctype)
    fields = [fieldname for fieldname in config["fields"] if fieldname == "name" or fieldname == "modified" or meta.has_field(fieldname)]
    filters: dict = {}
    context_branch = _context_branch()
    if context_branch:
        filters["service_branch"] = context_branch
    elif service_branch:
        filters["service_branch"] = service_branch
    if patient:
        filters["patient"] = patient
    if status:
        filters["status"] = status
    if resource == "vaccinations" and vaccine:
        filters["vaccine"] = vaccine
    date_field = config["date_field"]
    if from_date and to_date:
        filters[date_field] = ["between", [from_date, to_date]]
    elif from_date:
        filters[date_field] = [">=", from_date]
    elif to_date:
        filters[date_field] = ["<=", to_date]

    if resource == "lab-orders" and lab_test:
        parents = frappe.get_all(
            "Veterinary Lab Order Item",
            filters={"lab_test_template": lab_test},
            pluck="parent",
            limit_page_length=5000,
        )
        filters["name"] = ["in", parents or ["__no_matching_lab_order__"]]

    query = str(search or "").strip()
    search_fields = ["name"]
    for fieldname in fields:
        field = meta.get_field(fieldname)
        if field and field.fieldtype in {"Data", "Link", "Select", "Small Text"}:
            search_fields.append(fieldname)
    or_filters = (
        [[doctype, fieldname, "like", f"%{query}%"] for fieldname in list(dict.fromkeys(search_fields))[:6]]
        if query
        else None
    )

    page_length = min(max(cint(page_length) or 25, 1), legacy.PAGE_LENGTH_MAX)
    start = max(cint(start), 0)
    rows = frappe.get_list(
        doctype,
        fields=fields,
        filters=filters,
        or_filters=or_filters,
        order_by="modified desc",
        start=start,
        page_length=page_length,
    )
    total = legacy._permission_aware_count(doctype, filters, or_filters)
    columns = _columns(meta, fields)
    enrich_link_display_values(rows, columns)
    return {
        "resource": resource,
        "doctype": doctype,
        "title": resource_config["title"],
        "subtitle": resource_config["subtitle"],
        "columns": columns,
        "rows": rows,
        "start": start,
        "page_length": page_length,
        "total": total,
        "can_create": bool(frappe.has_permission(doctype, "create")),
        "can_quick_edit": False,
        "can_delete": False,
        "unsupported_required_fields": [],
        "full_form_route": legacy._full_form_route(doctype),
        "context_branch": context_branch,
        "summary_label": "Branch Scope",
        "summary_value": context_branch or "All permitted branches",
        "active_filters": {
            "patient": patient or "",
            "service_branch": filters.get("service_branch", ""),
            "status": status or "",
            "from_date": from_date or "",
            "to_date": to_date or "",
            "vaccine": vaccine or "",
            "lab_test": lab_test or "",
        },
    }


def _with_runtime_appointment_actions(resource: str, state: dict) -> dict:
    """Enrich the actual hooked Resource Center response with smart appointment actions."""
    if resource != "appointments":
        return state
    rows = state.get("rows") or []
    legacy._with_appointment_action_states({"key": "appointments"}, rows)
    return state


@frappe.whitelist()
def get_resource_page(
    resource: str,
    search: str = "",
    start: int = 0,
    page_length: int = 25,
    default_branch: str = "",
    status: str = "",
    registration_status: str = "",
    species: str = "",
    patient: str = "",
    service_branch: str = "",
    from_date: str = "",
    to_date: str = "",
    vaccine: str = "",
    lab_test: str = "",
) -> dict:
    if resource in CLINICAL_LIST_CONFIG:
        return _clinical_page(
            resource=resource,
            search=search,
            start=start,
            page_length=page_length,
            patient=patient,
            service_branch=service_branch,
            status=status,
            from_date=from_date,
            to_date=to_date,
            vaccine=vaccine,
            lab_test=lab_test,
        )

    state = v2._resource_page(
        resource=resource,
        search=search,
        start=start,
        page_length=page_length,
        default_branch=default_branch,
        status=status,
        registration_status=registration_status,
        species=species,
    )
    _with_runtime_appointment_actions(resource, state)
    state["unsupported_required_fields"] = []
    state["summary_label"] = "Branch Scope"
    state["summary_value"] = state.get("context_branch") or "All permitted branches"
    _hydrate_link_column_options(state)
    enrich_link_display_values(state.get("rows") or [], state.get("columns") or [])
    return state
