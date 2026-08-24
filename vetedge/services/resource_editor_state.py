from __future__ import annotations

import frappe
from frappe.utils import cint

from vetedge.coreedge_adapter import get_current_vetedge_branch
from vetedge.services.display_labels import get_display_label
from vetedge.services.permissions import can_access_branch_data, get_current_user
from vetedge.services.platform_access import require_vetedge_platform_access
from vetedge.services.portal_access import require_internal_user


INLINE_CREATE_DOCTYPES = {"Customer", "Veterinary Species", "Veterinary Breed"}


def _current_branch() -> str:
    try:
        value = str(get_current_vetedge_branch() or "").strip()
    except Exception:
        value = ""
    return "" if value.lower() in {"all", "all branches"} else value


def _operational_branch_field(doctype: str) -> str | None:
    meta = frappe.get_meta(doctype)
    for fieldname in ("service_branch", "branch"):
        if meta.has_field(fieldname):
            return fieldname
    return None


def _enforce_operational_branch_state(state: dict, name: str | None) -> dict:
    doctype = str(state.get("doctype") or "").strip()
    if not doctype:
        return state
    fieldname = _operational_branch_field(doctype)
    if not fieldname:
        return state

    values = state.setdefault("values", {})
    branch = str(values.get(fieldname) or "").strip()
    if name and not branch:
        branch = str(frappe.db.get_value(doctype, name, fieldname) or "").strip()
    if not name and not branch:
        branch = _current_branch()
        if branch:
            values[fieldname] = branch
    if branch:
        can_access_branch_data(get_current_user(), branch, raise_exception=True)
    return state


def _enforce_operational_branch_save(doctype: str, payload: dict, name: str | None) -> None:
    fieldname = _operational_branch_field(doctype)
    if not fieldname:
        return

    existing_branch = ""
    if name:
        existing_branch = str(frappe.db.get_value(doctype, name, fieldname) or "").strip()
        if existing_branch:
            can_access_branch_data(get_current_user(), existing_branch, raise_exception=True)

    requested_branch = str(payload.get(fieldname) or "").strip()
    if not name and not requested_branch:
        requested_branch = _current_branch()
        if requested_branch:
            payload[fieldname] = requested_branch
    if requested_branch:
        can_access_branch_data(get_current_user(), requested_branch, raise_exception=True)


def _normalize_link_schema(state: dict) -> dict:
    """Attach readable selected labels to Link fields for create and existing-record editors."""
    values = state.setdefault("values", {})
    fields = []
    for source in state.get("fields") or []:
        field = dict(source)
        if field.get("fieldtype") == "Link":
            target = str(field.get("options") or "").strip()
            fieldname = str(field.get("fieldname") or "").strip()
            value = values.get(fieldname)
            if target and value:
                field["selected_label"] = get_display_label(target, value)
            else:
                field["selected_label"] = ""
            field["can_create"] = bool(
                target in INLINE_CREATE_DOCTYPES and frappe.has_permission(target, "create")
            )
            if target == "Veterinary Breed":
                field["create_context_field"] = "species"
        fields.append(field)
    state["fields"] = fields
    return state


def _normalize_patient_schema(state: dict, name: str | None) -> dict:
    fields = []
    for source in state.get("fields") or []:
        field = dict(source)
        fieldname = field.get("fieldname")
        if not name and fieldname == "is_deceased":
            continue
        if not name and fieldname == "status":
            # A newly registered Patient always enters as living/Active. Status
            # can be changed later by an authorized edit; creation must not
            # accidentally imply a clinical life-state decision.
            field["options"] = "Active"
            field["default"] = "Active"
            field["read_only"] = 1
        if field.get("fieldtype") == "Check":
            value = state.setdefault("values", {}).get(fieldname, field.get("default", 0))
            state["values"][fieldname] = 1 if cint(value) else 0
            field["default"] = 1 if cint(field.get("default")) else 0
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
    state = _enforce_operational_branch_state(state, name)
    state = _normalize_link_schema(state)
    if resource == "patients":
        return _normalize_patient_schema(state, name)
    return state


@frappe.whitelist()
def save_resource_record(resource: str, values: str | dict, name: str | None = None) -> dict:
    require_internal_user()
    from vetedge.services.resource_center import _parse_values, _resource, save_resource_record as original

    config = _resource(resource)
    doctype = config["doctype"]
    require_vetedge_platform_access(
        action="save_resource_record",
        reference_doctype=doctype,
        reference_name=name,
    )

    payload = _parse_values(values)
    _enforce_operational_branch_save(doctype, payload, name)
    if resource == "patients" and not name:
        payload["status"] = "Active"
        payload["is_deceased"] = 0
        if not payload.get("default_branch"):
            payload["default_branch"] = _current_branch()
    return original(resource=resource, values=payload, name=name)
