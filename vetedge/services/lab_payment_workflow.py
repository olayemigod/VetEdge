from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint


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
        from vetedge.services.billing_core import get_payment_gate_status, resolve_billing_session

        session = resolve_billing_session(
            "Veterinary Lab Order",
            doc.name,
            include_closed_satisfied=True,
        )
        if not session:
            return {
                "can_proceed": False,
                "billable": True,
                "gate": "Billing Required",
                "message": _(
                    "Create the Lab Order invoice in Billing & Payment before laboratory processing can begin."
                ),
            }
        state = dict(get_payment_gate_status(session) or {})
        state.setdefault("billable", True)
        state.setdefault("gate", session.get("payment_gate_mode") or "Payment Gate")
        if not state.get("can_proceed") and not state.get("message"):
            state["message"] = _(
                "Complete the required Billing & Payment step before laboratory processing can continue."
            )
        return state

    invoice_name = doc.get("linked_invoice")
    if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
        return {
            "can_proceed": False,
            "billable": True,
            "gate": "Billing Required",
            "message": _("Create a Sales Invoice before laboratory processing can begin."),
        }
    invoice = frappe.db.get_value(
        "Sales Invoice",
        invoice_name,
        ["docstatus", "status", "outstanding_amount"],
        as_dict=True,
    )
    if not invoice or cint(invoice.get("docstatus")) != 1:
        return {
            "can_proceed": False,
            "billable": True,
            "gate": "Submitted Invoice Required",
            "message": _("Submit the linked Sales Invoice before laboratory processing can begin."),
        }
    return {
        "can_proceed": True,
        "billable": True,
        "gate": "Submitted Invoice",
        "message": _("The linked Sales Invoice is submitted."),
    }


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
