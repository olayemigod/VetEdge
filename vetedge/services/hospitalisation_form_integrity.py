from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from vetedge.services.hospitalisation_episode_policy import (
    ITEM_REQUIRED_ACTIVITY_TYPES,
    is_hospitalisation_dispensary_enabled,
)
from vetedge.services.hospitalisation_item_policy import _validate_activity_item
from vetedge.services.permissions import get_veterinary_doctor_users


ASSIGNMENT_DOCTYPE = "Branch Practitioner Assignment"
CARE_LOCATION_DOCTYPE = "Veterinary Care Location"
ACTIVITY_SIGNATURE_FIELDS = (
    "activity_type",
    "billable",
    "stock_affecting",
    "item",
    "qty",
    "uom",
    "source_warehouse",
)


def _clean(value: Any) -> str:
    return cstr(value or "").strip()


def _assignment_policy_enabled(branch: str | None) -> bool:
    branch = _clean(branch)
    if not branch or not frappe.db.exists("DocType", ASSIGNMENT_DOCTYPE):
        return False
    return bool(
        frappe.db.exists(
            ASSIGNMENT_DOCTYPE,
            {"branch": branch, "disabled": 0},
        )
    )


def _practitioner_assigned(practitioner: str | None, branch: str | None) -> bool:
    practitioner = _clean(practitioner)
    branch = _clean(branch)
    if not practitioner or not branch:
        return True
    if not _assignment_policy_enabled(branch):
        # Backward compatibility: Branch Practitioner Assignment is opt-in per
        # Branch. A Branch with no active assignment rows keeps the legacy
        # VetEdge Doctor list until administrators configure the master.
        return True
    return bool(
        frappe.db.exists(
            ASSIGNMENT_DOCTYPE,
            {"branch": branch, "practitioner": practitioner, "disabled": 0},
        )
    )


def _field_changed(doc, previous, fieldname: str) -> bool:
    if doc.is_new() or previous is None:
        return True
    return _clean(doc.get(fieldname)) != _clean(previous.get(fieldname))


def _row_signature(row) -> tuple:
    values = []
    for fieldname in ACTIVITY_SIGNATURE_FIELDS:
        value = row.get(fieldname)
        if fieldname in {"billable", "stock_affecting"}:
            value = cint(value)
        elif fieldname == "qty":
            value = flt(value)
        else:
            value = _clean(value)
        values.append(value)
    return tuple(values)


def _changed_activity_rows(doc, previous) -> list:
    if doc.is_new() or previous is None:
        return list(doc.get("activities") or [])
    old_rows = {row.name: row for row in (previous.get("activities") or []) if row.name}
    changed = []
    for row in doc.get("activities") or []:
        old = old_rows.get(row.name)
        if old is None or _row_signature(row) != _row_signature(old):
            changed.append(row)
    return changed


def _validate_practitioner_branch(doc, previous) -> None:
    if not (_field_changed(doc, previous, "service_branch") or _field_changed(doc, previous, "attending_veterinarian")):
        return
    branch = _clean(doc.get("service_branch"))
    practitioner = _clean(doc.get("attending_veterinarian"))
    if practitioner and branch and not _practitioner_assigned(practitioner, branch):
        frappe.throw(
            _("Attending Veterinarian {0} is not assigned to Veterinary Branch {1}.").format(
                practitioner,
                branch,
            ),
            frappe.ValidationError,
        )


def _validate_care_location_branch(doc, previous) -> None:
    if not (_field_changed(doc, previous, "service_branch") or _field_changed(doc, previous, "care_location")):
        return
    location_name = _clean(doc.get("care_location"))
    branch = _clean(doc.get("service_branch"))
    if not location_name:
        return
    location = frappe.db.get_value(
        CARE_LOCATION_DOCTYPE,
        location_name,
        ["name", "branch", "enabled", "status"],
        as_dict=True,
    ) or {}
    if not location:
        frappe.throw(_("Select a valid Veterinary Care Location."), frappe.ValidationError)
    if _clean(location.get("branch")) and _clean(location.get("branch")) != branch:
        frappe.throw(_("Care Location Branch must match the Hospitalisation Branch."), frappe.ValidationError)
    if not cint(location.get("enabled")):
        frappe.throw(_("Selected Care Location is disabled."), frappe.ValidationError)


def _validate_changed_activities(doc, previous) -> None:
    dispensary_enabled = is_hospitalisation_dispensary_enabled()
    for row in _changed_activity_rows(doc, previous):
        activity_type = _clean(row.get("activity_type")) or "Other"
        billable = bool(cint(row.get("billable")))
        stock_affecting = bool(cint(row.get("stock_affecting")))
        item = _clean(row.get("item")) or None

        if stock_affecting and not dispensary_enabled and not row.get("stock_entry"):
            # Match the Episode workflow: Dispensary Flow off means new/edited
            # unposted rows cannot create a stock obligation.
            row.stock_affecting = 0
            row.stock_status = "Not Applicable"
            row.source_warehouse = None
            stock_affecting = False

        if (billable or stock_affecting or activity_type in ITEM_REQUIRED_ACTIVITY_TYPES) and not item:
            frappe.throw(
                _(
                    "ERPNext Item is required for billable, stock-affecting, Medication and Fluid Therapy Hospitalisation activities."
                ),
                frappe.ValidationError,
            )

        if item:
            _validate_activity_item(
                item,
                billable=billable,
                stock_affecting=stock_affecting,
            )
            if flt(row.get("qty")) <= 0:
                frappe.throw(_("Hospitalisation activity quantity must be greater than zero."), frappe.ValidationError)


def enforce_hospitalisation_form_integrity(doc) -> None:
    """Protect the native fallback form without invalidating untouched history."""
    previous = None if doc.is_new() else doc.get_doc_before_save()
    _validate_practitioner_branch(doc, previous)
    _validate_care_location_branch(doc, previous)
    _validate_changed_activities(doc, previous)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_hospitalisation_practitioners(doctype, txt, searchfield, start, page_len, filters):
    filters = filters or {}
    if isinstance(filters, str):
        filters = frappe.parse_json(filters) or {}
    branch = _clean(filters.get("branch")) if isinstance(filters, dict) else ""
    if not _assignment_policy_enabled(branch):
        return get_veterinary_doctor_users(doctype, txt, searchfield, start, page_len, filters)

    search = f"%{txt}%"
    return frappe.db.sql(
        """
        SELECT DISTINCT
            user.name,
            COALESCE(NULLIF(user.full_name, ''), user.email, user.name)
        FROM `tabUser` user
        INNER JOIN `tabHas Role` has_role
            ON has_role.parent = user.name
            AND has_role.parenttype = 'User'
            AND has_role.role = 'VetEdge Doctor'
        INNER JOIN `tabBranch Practitioner Assignment` assignment
            ON assignment.practitioner = user.name
            AND assignment.branch = %(branch)s
            AND assignment.disabled = 0
        WHERE user.enabled = 1
            AND user.user_type = 'System User'
            AND (
                user.name LIKE %(search)s
                OR user.full_name LIKE %(search)s
                OR user.email LIKE %(search)s
            )
        ORDER BY COALESCE(NULLIF(user.full_name, ''), user.email, user.name) ASC
        LIMIT %(start)s, %(page_len)s
        """,
        {
            "branch": branch,
            "search": search,
            "start": max(cint(start), 0),
            "page_len": min(max(cint(page_len) or 20, 1), 50),
        },
    )


@frappe.whitelist()
@frappe.read_only()
def is_hospitalisation_practitioner_allowed(branch: str | None, practitioner: str | None) -> bool:
    return _practitioner_assigned(practitioner, branch)


@frappe.whitelist()
def search_hospitalisation_episode_options(
    hospitalisation_name: str,
    field: str,
    txt: str = "",
    start: int | str = 0,
    page_length: int | str = 20,
):
    if field != "practitioner":
        from vetedge.services.hospitalisation_item_policy import search_hospitalisation_episode_options as original

        return original(
            hospitalisation_name=hospitalisation_name,
            field=field,
            txt=txt,
            start=start,
            page_length=page_length,
        )

    from vetedge.services import hospitalisation_episode_policy as episode_policy

    doc = episode_policy._load_hospitalisation(hospitalisation_name)
    rows = search_hospitalisation_practitioners(
        "User",
        txt,
        "name",
        start,
        page_length,
        {"branch": doc.get("service_branch")},
    )
    return [{"value": row[0], "label": row[1]} for row in rows]
