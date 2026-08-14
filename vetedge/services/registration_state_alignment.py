from __future__ import annotations

import frappe
from frappe.utils import flt


def align_patient_registration_state(doc, method: str | None = None) -> None:
    """Keep Patient registration status aligned with billable registration state."""
    from vetedge.services.registration_billing import (
        AWAITING_PAYMENT_STATUS,
        PAID_STATUS,
        get_registration_rule,
        set_patient_registration_fields,
    )

    patient_name = doc.get("name")
    if not patient_name:
        return

    rule = get_registration_rule(doc.get("default_branch"))
    if not rule.enabled or flt(rule.registration_fee) <= 0:
        return

    current_status = frappe.db.get_value("Veterinary Patient", patient_name, "registration_status") or doc.get(
        "registration_status"
    )
    if current_status == PAID_STATUS:
        return

    invoice_name = frappe.db.get_value("Veterinary Patient", patient_name, "registration_invoice")
    if invoice_name and frappe.db.exists("Sales Invoice", invoice_name):
        invoice = frappe.db.get_value(
            "Sales Invoice",
            invoice_name,
            ["docstatus", "status", "outstanding_amount"],
            as_dict=True,
        )
        if invoice and int(invoice.get("docstatus") or 0) == 1 and flt(invoice.get("outstanding_amount")) <= 0:
            return

    set_patient_registration_fields(
        patient_name,
        registration_status=AWAITING_PAYMENT_STATUS,
        registration_fee_amount=rule.registration_fee,
    )


def align_registration_state_from_invoice(doc, method: str | None = None) -> None:
    """Re-align linked Patients after invoice lifecycle handlers run.

    Registration billing clears a cancelled invoice link. A billable registration
    is still pending after that cancellation, so it must not fall back to the
    misleading generic Registered state.
    """
    patients = frappe.get_all(
        "Veterinary Patient",
        filters={"registration_invoice": doc.name},
        pluck="name",
    )
    if not patients and int(doc.get("docstatus") or 0) == 2:
        # The primary billing hook may already have cleared registration_invoice.
        # Search recently modified billable Patients is unsafe and unnecessary;
        # cancellation callers pass through before the link is cleared in normal
        # event ordering. If it is already cleared, the row-level action still
        # derives the pending fee from its branch rule on the next Resource Center load.
        return
    for patient in patients:
        patient_doc = frappe.get_doc("Veterinary Patient", patient)
        align_patient_registration_state(patient_doc, method)
