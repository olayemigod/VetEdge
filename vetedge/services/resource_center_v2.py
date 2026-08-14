from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt

from vetedge.coreedge_adapter import get_current_vetedge_branch
from vetedge.services import resource_center as legacy


PATIENT_DISPLAY_FIELDS = [
    "name",
    "patient_name",
    "status",
    "registration_status",
    "primary_owner",
    "default_branch",
    "species",
    "modified",
]
PATIENT_QUERY_FIELDS = [
    *PATIENT_DISPLAY_FIELDS,
    "registration_invoice",
    "registration_billed",
    "registration_fee_amount",
]
PATIENT_SEARCH_FIELDS = [
    "name",
    "patient_name",
    "primary_owner",
    "species",
    "breed",
    "microchip_id",
    "registration_status",
]


def _context_branch() -> str | None:
    try:
        branch = get_current_vetedge_branch()
    except Exception:
        branch = None
    branch = str(branch or "").strip()
    if not branch or branch.lower() in {"all", "all branches"}:
        return None
    return branch


def _branch_field(meta) -> str | None:
    for fieldname in ("branch", "service_branch", "default_branch"):
        if meta.has_field(fieldname):
            return fieldname
    return None


def _base_filters(meta) -> dict:
    branch = _context_branch()
    fieldname = _branch_field(meta)
    return {fieldname: branch} if branch and fieldname else {}


def _patient_filters(meta, default_branch: str, status: str, registration_status: str, species: str) -> dict:
    filters = _base_filters(meta)
    context_branch = filters.get("default_branch")
    requested_branch = str(default_branch or "").strip()
    if requested_branch and not context_branch:
        filters["default_branch"] = requested_branch
    if status:
        filters["status"] = str(status).strip()
    if registration_status:
        filters["registration_status"] = str(registration_status).strip()
    if species:
        filters["species"] = str(species).strip()
    return filters


def _patient_columns() -> list[dict]:
    return [
        {"fieldname": "name", "label": _("ID"), "fieldtype": "Data"},
        {"fieldname": "patient_name", "label": _("Patient Name"), "fieldtype": "Data"},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Select"},
        {"fieldname": "registration_payment_state", "label": _("Registration"), "fieldtype": "Data"},
        {"fieldname": "primary_owner", "label": _("Primary Owner"), "fieldtype": "Link"},
        {"fieldname": "default_branch", "label": _("Default Branch"), "fieldtype": "Link"},
        {"fieldname": "species", "label": _("Species"), "fieldtype": "Link"},
        {"fieldname": "modified", "label": _("Modified"), "fieldtype": "Datetime"},
    ]


def _invoice_state_map(rows: list) -> dict[str, dict]:
    names = list({str(row.get("registration_invoice")) for row in rows if row.get("registration_invoice")})
    if not names or not frappe.has_permission("Sales Invoice", "read"):
        return {}
    invoices = frappe.get_list(
        "Sales Invoice",
        filters={"name": ["in", names]},
        fields=["name", "docstatus", "status", "grand_total", "outstanding_amount"],
        page_length=len(names),
    )
    return {row.name: dict(row) for row in invoices}


def _registration_rule_cache(rows: list) -> dict[str, object]:
    from vetedge.services.registration_billing import get_registration_rule

    cache: dict[str, object] = {}
    for row in rows:
        branch = str(row.get("default_branch") or "")
        if branch not in cache:
            cache[branch] = get_registration_rule(branch or None)
    return cache


def _registration_action(row, invoice: dict | None, rule) -> dict:
    from vetedge.services.registration_billing import PAID_STATUS

    enabled = bool(getattr(rule, "enabled", False))
    fee = flt(row.get("registration_fee_amount") or getattr(rule, "registration_fee", 0))
    if not enabled or fee <= 0:
        return {
            "state": "Not Required",
            "label": "",
            "tone": "muted",
            "enabled": False,
        }

    if str(row.get("registration_status") or "") == PAID_STATUS:
        return {
            "state": "Paid",
            "label": _("View Registration Payment"),
            "tone": "success",
            "enabled": True,
        }

    if not row.get("registration_invoice"):
        return {
            "state": "Not Billed",
            "label": _("Bill Registration"),
            "tone": "primary",
            "enabled": True,
        }

    if not invoice:
        return {
            "state": str(row.get("registration_status") or _("Billing Pending")),
            "label": _("View Registration Billing"),
            "tone": "default",
            "enabled": True,
        }

    docstatus = cint(invoice.get("docstatus"))
    outstanding = flt(invoice.get("outstanding_amount"))
    grand_total = flt(invoice.get("grand_total"))
    paid = max(grand_total - outstanding, 0)
    if docstatus == 2:
        return {
            "state": "Cancelled",
            "label": _("Rebill Registration"),
            "tone": "warning",
            "enabled": True,
        }
    if docstatus == 0:
        return {
            "state": "Draft Invoice",
            "label": _("Submit Registration Invoice"),
            "tone": "warning",
            "enabled": True,
        }
    if docstatus == 1 and outstanding <= 0:
        return {
            "state": "Paid",
            "label": _("View Registration Payment"),
            "tone": "success",
            "enabled": True,
        }
    if docstatus == 1 and paid > 0:
        return {
            "state": "Partly Paid",
            "label": _("Pay Registration Balance"),
            "tone": "warning",
            "enabled": True,
        }
    return {
        "state": "Unpaid",
        "label": _("Pay Registration"),
        "tone": "primary",
        "enabled": True,
    }


def _enrich_patient_rows(rows: list) -> None:
    invoices = _invoice_state_map(rows)
    rules = _registration_rule_cache(rows)
    for row in rows:
        invoice_name = row.get("registration_invoice")
        action = _registration_action(
            row,
            invoices.get(str(invoice_name)) if invoice_name else None,
            rules.get(str(row.get("default_branch") or "")),
        )
        row["registration_payment_state"] = action["state"]
        row["_registration_action"] = action


def _resource_page(
    resource: str,
    search: str,
    start: int,
    page_length: int,
    default_branch: str = "",
    status: str = "",
    registration_status: str = "",
    species: str = "",
) -> dict:
    legacy._require_login()
    config = legacy._resource(resource)
    doctype = config["doctype"]
    if not frappe.has_permission(doctype, "read"):
        frappe.throw(_("You are not permitted to view {0}.").format(doctype), frappe.PermissionError)

    meta = frappe.get_meta(doctype)
    is_patients = config["key"] == "patients"
    fields = list(PATIENT_QUERY_FIELDS if is_patients else legacy._list_fields(meta))
    filters = (
        _patient_filters(meta, default_branch, status, registration_status, species)
        if is_patients
        else _base_filters(meta)
    )
    query = str(search or "").strip()
    search_fields = PATIENT_SEARCH_FIELDS if is_patients else legacy._search_fields(meta, fields)
    or_filters = (
        [[doctype, fieldname, "like", f"%{query}%"] for fieldname in search_fields if meta.has_field(fieldname) or fieldname == "name"]
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
    unsupported = legacy._unsupported_required_fields(meta)
    can_create = bool(config["allow_create"] and frappe.has_permission(doctype, "create") and not unsupported)
    can_quick_edit = bool(config["allow_edit"] and frappe.has_permission(doctype, "write") and not unsupported)
    can_delete = bool(config["allow_delete"] and frappe.has_permission(doctype, "delete"))

    if is_patients:
        _enrich_patient_rows(rows)

    return {
        "resource": config["key"],
        "doctype": doctype,
        "title": config["title"],
        "subtitle": config["subtitle"],
        "columns": _patient_columns() if is_patients else legacy._column_schema(meta, fields),
        "rows": rows,
        "start": start,
        "page_length": page_length,
        "total": total,
        "can_create": can_create,
        "can_quick_edit": can_quick_edit,
        "can_delete": can_delete,
        "unsupported_required_fields": unsupported,
        "full_form_route": legacy._full_form_route(doctype),
        "context_branch": _context_branch(),
        "active_filters": {
            "default_branch": filters.get("default_branch", "") if is_patients else "",
            "status": filters.get("status", "") if is_patients else "",
            "registration_status": filters.get("registration_status", "") if is_patients else "",
            "species": filters.get("species", "") if is_patients else "",
        },
    }


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
) -> dict:
    return _resource_page(
        resource=resource,
        search=search,
        start=start,
        page_length=page_length,
        default_branch=default_branch,
        status=status,
        registration_status=registration_status,
        species=species,
    )
