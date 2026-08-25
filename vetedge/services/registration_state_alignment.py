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


def update_registration_status_from_invoice_aligned(doc, method: str | None = None) -> None:
    """Run canonical registration invoice sync, then correct billable pending state."""
    from vetedge.services.registration_billing import update_registration_status_from_invoice

    patients = frappe.get_all(
        "Veterinary Patient",
        filters={"registration_invoice": doc.name},
        pluck="name",
    )
    update_registration_status_from_invoice(doc, method)
    for patient in patients:
        if frappe.db.exists("Veterinary Patient", patient):
            align_patient_registration_state(frappe.get_doc("Veterinary Patient", patient), method)


def update_registration_status_from_payment_entry_aligned(doc, method: str | None = None) -> None:
    """Run canonical Payment Entry sync and re-evaluate linked registrations."""
    from vetedge.services.registration_billing import update_registration_status_from_payment_entry

    invoice_names = [
        reference.reference_name
        for reference in doc.get("references") or []
        if reference.reference_doctype == "Sales Invoice" and reference.reference_name
    ]
    patients = []
    if invoice_names:
        patients = frappe.get_all(
            "Veterinary Patient",
            filters={"registration_invoice": ["in", invoice_names]},
            pluck="name",
        )
    update_registration_status_from_payment_entry(doc, method)
    for patient in patients:
        if frappe.db.exists("Veterinary Patient", patient):
            align_patient_registration_state(frappe.get_doc("Veterinary Patient", patient), method)
