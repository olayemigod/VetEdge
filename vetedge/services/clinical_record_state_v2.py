from __future__ import annotations

import frappe

from vetedge.services.display_labels import get_display_label
from vetedge.services.portal_access import require_internal_user


VACCINATION_SYSTEM_FIELDS = {
    "administered_by",
    "administered_on",
    "next_vaccination_appointment",
    "batch_no",
    "expiry_date",
    "billing_item",
    "amount",
    "linked_invoice",
    "stock_entry_reference",
}
PRE_ADMIN_STATUSES = {"Draft", "Awaiting Payment", "Pending Administration"}


def _field_map(state: dict) -> dict[str, dict]:
    return {str(field.get("fieldname") or ""): field for field in state.get("fields") or []}


def _align_link_labels(state: dict) -> dict:
    for field in state.get("fields") or []:
        if field.get("fieldtype") != "Link" or not field.get("value"):
            continue
        field["selected_label"] = get_display_label(field.get("options"), field.get("value"))
    return state


def _align_vaccination_state(state: dict) -> dict:
    fields = _field_map(state)
    status = str(state.get("status") or "Draft")
    billing = state.get("billing_state") or {}
    submitted = bool(billing.get("has_submitted_invoice"))
    administered = status == "Administered"
    stock_posted = bool(fields.get("stock_entry_reference", {}).get("value"))

    for fieldname in VACCINATION_SYSTEM_FIELDS:
        field = fields.get(fieldname)
        if field:
            field["read_only"] = 1

    for fieldname in ("administered_by", "administered_on"):
        field = fields.get(fieldname)
        if field and status in PRE_ADMIN_STATUSES:
            field["value"] = ""
            field["selected_label"] = ""

    consultation = fields.get("linked_consultation")
    if consultation:
        consultation["read_only"] = int(submitted or administered or stock_posted)

    vaccine = fields.get("vaccine")
    if vaccine:
        vaccine["read_only"] = int(submitted or administered or stock_posted)

    rate = fields.get("rate")
    if rate:
        rate["read_only"] = int(submitted or administered or stock_posted)

    next_due = fields.get("next_due_date")
    if next_due:
        next_due["read_only"] = int(stock_posted and administered)

    state["can_save"] = bool(
        state.get("can_save") and any(not field.get("read_only") for field in fields.values())
    )
    return state


@frappe.whitelist()
def get_clinical_record_editor(doctype: str, name: str) -> dict:
    require_internal_user()
    from vetedge.services.clinical_record_state import get_clinical_record_editor as original

    state = _align_link_labels(original(doctype=doctype, name=name))
    if doctype == "Veterinary Vaccination Record":
        state = _align_vaccination_state(state)
    return state


@frappe.whitelist()
def get_lab_result_editor(lab_order: str, row_name: str) -> dict:
    require_internal_user()
    from vetedge.services.clinical_record_state import get_lab_result_editor as original

    return original(lab_order=lab_order, row_name=row_name)
