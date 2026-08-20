from __future__ import annotations

import frappe
from frappe import _


SERVICE_PROGRESS_STATUSES = {
    "Sample Collected",
    "Sent to Lab",
    "In Progress",
    "Result Pending",
    "Result Entered",
    "Awaiting Review",
    "Reviewed",
    "Completed",
}
RESULT_CONTENT_FIELDS = (
    "result_value",
    "result_text",
    "result_attachment",
    "remarks",
    "abnormal_flag",
)


def _standalone_lab_payment_gate_mode() -> str:
    from vetedge.services.payment_gate import FULL_PAYMENT_REQUIRED

    if not frappe.db.exists("DocType", "Veterinary Settings"):
        return FULL_PAYMENT_REQUIRED
    meta = frappe.get_meta("Veterinary Settings")
    if not meta.has_field("default_payment_gate_mode"):
        return FULL_PAYMENT_REQUIRED
    return frappe.db.get_single_value("Veterinary Settings", "default_payment_gate_mode") or FULL_PAYMENT_REQUIRED


def get_lab_service_payment_gate_state(doc) -> dict:
    """Return the same payment readiness used to permit laboratory service work.

    Creating/ordering a Lab Order is allowed before payment so Front Desk can
    establish the service and billing source. Once clinical/laboratory work is
    about to start, the configured billing gate becomes authoritative.
    """
    from vetedge.services.lab import lab_order_has_billable_items, use_billing_core_for_lab_order

    if not lab_order_has_billable_items(doc):
        return {
            "can_proceed": True,
            "billable": False,
            "gate": "No Billable Items",
            "message": _("This Lab Order has no billable tests, so billing does not block laboratory work."),
        }

    if use_billing_core_for_lab_order() and doc.get("name"):
        from vetedge.services.lab_billing_context import get_lab_billing_core_gate_state

        return get_lab_billing_core_gate_state(doc)

    invoice_name = doc.get("linked_invoice")
    if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
        return {
            "can_proceed": False,
            "billable": True,
            "gate": "Billing Required",
            "message": _("Create a Sales Invoice before laboratory processing can begin."),
        }

    from vetedge.services.payment_gate import evaluate_invoice_payment_gate, get_consultation_payment_gate

    mode = get_consultation_payment_gate() if doc.get("consultation") else _standalone_lab_payment_gate_mode()
    state = dict(evaluate_invoice_payment_gate(invoice_name, mode, "laboratory") or {})
    state["billable"] = True
    state["billing_context"] = "consultation" if doc.get("consultation") else "standalone_lab"
    state["invoices"] = [invoice_name]
    return state


def _row_key(row) -> str:
    return str(row.get("name") or row.get("lab_test_template") or row.get("idx") or "")


def _result_content_changed(doc, previous) -> bool:
    if not previous:
        return False
    previous_rows = {_row_key(row): row for row in previous.get("lab_tests") or []}
    for row in doc.get("lab_tests") or []:
        before = previous_rows.get(_row_key(row))
        if not before:
            if any(row.get(fieldname) not in (None, "", 0) for fieldname in RESULT_CONTENT_FIELDS):
                return True
            continue
        for fieldname in RESULT_CONTENT_FIELDS:
            if row.get(fieldname) != before.get(fieldname):
                return True
    return False


def lab_change_starts_or_advances_service(doc, previous) -> bool:
    if not previous:
        return False
    current_status = str(doc.get("status") or "")
    previous_status = str(previous.get("status") or "")
    if current_status == "Cancelled":
        return False
    if current_status != previous_status and current_status in SERVICE_PROGRESS_STATUSES:
        return True
    return _result_content_changed(doc, previous)


def enforce_lab_service_payment_gate(doc, method: str | None = None) -> None:
    """Block both native-form and EdgeSuite workflow bypasses when billing is blocked."""
    previous = doc.get_doc_before_save() if getattr(doc, "get_doc_before_save", None) else None
    if not lab_change_starts_or_advances_service(doc, previous):
        return
    state = get_lab_service_payment_gate_state(doc)
    if state.get("can_proceed"):
        return
    frappe.throw(
        state.get("message")
        or _("Complete Billing & Payment before laboratory processing can continue."),
        frappe.ValidationError,
    )
