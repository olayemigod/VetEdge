from __future__ import annotations

import frappe

from vetedge.services.portal_access import require_internal_user


def _can_submit_invoice(invoice_name: str | None) -> bool:
    if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
        return False
    invoice = frappe.get_doc("Sales Invoice", invoice_name)
    return bool(frappe.has_permission("Sales Invoice", "submit", doc=invoice))


def _can_record_payment() -> bool:
    # The final Payment Entry is still checked again with its populated document
    # by record_modal_invoice_payment. These role-level checks keep the UI from
    # advertising an action that the user cannot normally create/submit at all.
    return bool(
        frappe.has_permission("Payment Entry", "create")
        and frappe.has_permission("Payment Entry", "submit")
    )


def _apply_row_permissions(rows: list[dict] | None, can_pay: bool) -> None:
    for row in rows or []:
        invoice_name = row.get("name") or row.get("invoice")
        if row.get("can_submit_invoice"):
            row["can_submit_invoice"] = _can_submit_invoice(invoice_name)
        if row.get("can_pay_outstanding") or row.get("can_pay"):
            allowed = bool(can_pay and invoice_name)
            row["can_pay_outstanding"] = allowed
            row["can_pay"] = allowed
            if not allowed and row.get("action_label") == "Pay Outstanding":
                row["action_label"] = "View"


def _primary_invoice_name(state: dict) -> str | None:
    invoice = state.get("invoice") or {}
    return (
        invoice.get("name")
        or state.get("current_draft_invoice")
        or state.get("open_invoice_name")
        or state.get("latest_invoice")
    )


@frappe.whitelist()
def get_billing_modal_state(source_doctype: str, source_name: str) -> dict:
    require_internal_user()
    from vetedge.services.billing_modal import get_billing_modal_state as original

    state = original(source_doctype=source_doctype, source_name=source_name)
    actions = state.get("actions") or {}
    can_pay = _can_record_payment()
    invoice_name = _primary_invoice_name(state)

    if actions.get("can_submit_invoice"):
        actions["can_submit_invoice"] = _can_submit_invoice(invoice_name)
    if actions.get("can_record_payment"):
        actions["can_record_payment"] = can_pay

    _apply_row_permissions(state.get("invoice_history"), can_pay)
    _apply_row_permissions(state.get("billing_group_invoice_history"), can_pay)
    _apply_row_permissions(state.get("patient_outstanding_context"), can_pay)

    # Keep top-level compatibility fields synchronized with the permission-aware
    # action object consumed by the shared billing modal.
    state["actions"] = actions
    return state
