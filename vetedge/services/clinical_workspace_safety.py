from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

CLINICAL_WORKSPACE_SAVE_COMMAND = "vetedge.services.clinical_workspace.save_consultation_document"
LOCKED_BILLING_STATUSES = {"Submitted Invoiced", "Paid", "Cancelled", "Skipped"}
LOCKED_PAYMENT_STATUSES = {"Partly Paid", "Paid", "Cancelled"}
SOURCE_CONTROLLED_TYPES = {"Lab Order", "Vaccination"}
PROTECTED_EDIT_FIELDS = (
    "item",
    "description",
    "qty",
    "uom",
    "rate",
    "service_type",
    "treatment_type",
    "notes",
)
NUMERIC_FIELDS = {"qty", "rate"}


def enforce_clinical_workspace_treatment_row_safety(doc, method: str | None = None) -> None:
    """Prevent Clinical Workspace payloads from deleting or editing source/financially locked rows.

    The native consultation controller remains authoritative for normal saves. This additional
    guard applies only to the dedicated Clinical Workspace endpoint, where child rows arrive as
    a curated JSON payload and hidden billing/source fields are intentionally not user editable.
    """
    if getattr(doc, "doctype", None) != "Veterinary Consultation":
        return
    if _request_command() != CLINICAL_WORKSPACE_SAVE_COMMAND:
        return
    previous = doc.get_doc_before_save() if getattr(doc, "get_doc_before_save", None) else None
    if not previous:
        return

    current_by_name = {
        row.get("name"): row
        for row in doc.get("planned_treatments") or []
        if row.get("name")
    }
    for old_row in previous.get("planned_treatments") or []:
        if not _is_protected_row(old_row):
            continue
        row_name = old_row.get("name")
        current = current_by_name.get(row_name)
        if not current:
            frappe.throw(
                _("Treatment row {0} is controlled by billing or its source document and cannot be removed here.").format(
                    row_name or old_row.get("item") or _("Unknown")
                ),
                frappe.ValidationError,
            )
        changed = [
            fieldname
            for fieldname in PROTECTED_EDIT_FIELDS
            if not _same_value(fieldname, old_row.get(fieldname), current.get(fieldname))
        ]
        if changed:
            frappe.throw(
                _(
                    "Treatment row {0} is controlled by billing or its source document. "
                    "Update the originating Lab Order, Vaccination, or billing workflow instead."
                ).format(row_name or old_row.get("item") or _("Unknown")),
                frappe.ValidationError,
            )


def _request_command() -> str:
    form_dict = getattr(frappe.local, "form_dict", None) or getattr(frappe, "form_dict", None)
    if not form_dict:
        return ""
    getter = getattr(form_dict, "get", None)
    return str(getter("cmd") if callable(getter) else getattr(form_dict, "cmd", "") or "")


def _is_protected_row(row) -> bool:
    return bool(
        row.get("source_type") in SOURCE_CONTROLLED_TYPES
        or row.get("billing_status") in LOCKED_BILLING_STATUSES
        or row.get("payment_status") in LOCKED_PAYMENT_STATUSES
    )


def _same_value(fieldname: str, old_value, new_value) -> bool:
    if fieldname in NUMERIC_FIELDS:
        return flt(old_value) == flt(new_value)
    return (old_value or "") == (new_value or "")
