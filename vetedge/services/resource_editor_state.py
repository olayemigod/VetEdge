from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from vetedge.coreedge_adapter import get_current_vetedge_branch
from vetedge.services.portal_access import require_internal_user


INLINE_CREATE_DOCTYPES = {"Customer", "Veterinary Species", "Veterinary Breed"}


def _current_branch() -> str:
    try:
        value = str(get_current_vetedge_branch() or "").strip()
    except Exception:
        value = ""
    return "" if value.lower() in {"all", "all branches"} else value


def _display_label(doctype: str, value: str | None) -> str:
    if not value:
        return ""
    if doctype == "Customer":
        return frappe.db.get_value("Customer", value, "customer_name") or value
    if doctype == "Veterinary Species":
        return frappe.db.get_value(doctype, value, "species_name") or value
    if doctype == "Veterinary Breed":
        return frappe.db.get_value(doctype, value, "breed_name") or value
    if doctype == "Veterinary Patient":
        return frappe.db.get_value(doctype, value, "patient_name") or value
    return value


def _normalize_patient_schema(state: dict, name: str | None) -> dict:
    fields = []
    for source in state.get("fields") or []:
        field = dict(source)
        fieldname = field.get("fieldname")
        if not name and fieldname == "is_deceased":
            continue
        if not name and fieldname == "status":
            field["options"] = "Active\nInactive"
            field["default"] = "Active"
        if field.get("fieldtype") == "Check":
            value = state.setdefault("values", {}).get(fieldname, field.get("default", 0))
            state["values"][fieldname] = 1 if cint(value) else 0
            field["default"] = 1 if cint(field.get("default")) else 0
        if field.get("fieldtype") == "Link":
            target = str(field.get("options") or "")
            value = state.setdefault("values", {}).get(fieldname)
            field["selected_label"] = _display_label(target, value)
            field["can_create"] = bool(
                target in INLINE_CREATE_DOCTYPES and frappe.has_permission(target, "create")
            )
            if target == "Veterinary Breed":
                field["create_context_field"] = "species"
        fields.append(field)
    state["fields"] = fields
    if not name:
        values = state.setdefault("values", {})
        values["status"] = "Active"
        values["is_deceased"] = 0
        if not values.get("default_branch"):
            values["default_branch"] = _current_branch()
    return state


@frappe.whitelist()
def get_resource_editor(resource: str, name: str | None = None) -> dict:
    require_internal_user()
    from vetedge.services.resource_center import get_resource_editor as original

    state = original(resource=resource, name=name)
    if resource == "patients":
        return _normalize_patient_schema(state, name)
    return state


@frappe.whitelist()
def save_resource_record(resource: str, values: str | dict, name: str | None = None) -> dict:
    require_internal_user()
    from vetedge.services.resource_center import _parse_values, save_resource_record as original

    payload = _parse_values(values)
    if resource == "patients" and not name:
        payload["status"] = "Active"
        payload["is_deceased"] = 0
        if not payload.get("default_branch"):
            payload["default_branch"] = _current_branch()
    return original(resource=resource, values=payload, name=name)
