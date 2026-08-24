from __future__ import annotations

import frappe
from frappe.utils import now_datetime, nowdate

from vetedge.services.boarding import (
    PET_BOARDING_BOOKING_DOCTYPE,
    PET_BOARDING_STAY_DOCTYPE,
    calculate_boarding_charges,
    emit_boarding_event,
    ensure_booking_transition_allowed,
    get_existing_active_stay,
    use_billing_core_for_boarding,
    validate_boarding_checkout_billing as validate_legacy_boarding_checkout_billing,
)


def validate_boarding_checkout_billing_aligned(doc) -> None:
    """Validate checkout against the billing authority used for this booking.

    Billing Core sessions are the authoritative charge/invoice ledger when they
    are enabled. Re-scanning only the linked Sales Invoice item rows can produce
    a false delta after the source charge has already been synchronized through
    Billing Core. Legacy sites retain the existing invoice-item reconciliation.
    """
    charges = calculate_boarding_charges(doc)
    doc.daily_rate = charges["daily_rate"]
    doc.billable_days = charges["billable_days"]
    doc.total_boarding_charge = charges["total_boarding_charge"]

    if not use_billing_core_for_boarding():
        validate_legacy_boarding_checkout_billing(doc)
        return

    from vetedge.services.billing_core import (
        get_source_payment_gate_status,
        resolve_billing_session,
        sync_source_to_billing_session,
    )

    # Always resynchronize the current stay charge before evaluating checkout.
    # If a submitted invoice no longer matches the current charge, Billing Core
    # will retain/create pending charge evidence and the gate will fail closed.
    sync_source_to_billing_session(PET_BOARDING_BOOKING_DOCTYPE, doc.name)
    session = resolve_billing_session(PET_BOARDING_BOOKING_DOCTYPE, doc.name)
    status = get_source_payment_gate_status(PET_BOARDING_BOOKING_DOCTYPE, doc.name)

    if not session and not status.get("invoices"):
        frappe.throw(
            "Create the boarding invoice before checking out this booking.",
            frappe.ValidationError,
        )
    if not status.get("can_proceed"):
        frappe.throw(
            status.get("message")
            or "Submit and fully pay the current boarding charges before checking out this booking.",
            frappe.ValidationError,
        )


def check_out_boarding_booking_doc_aligned(doc) -> dict:
    """Checkout using Billing Core truth without mutating submitted invoices."""
    ensure_booking_transition_allowed(doc.status, "Checked Out")
    if not doc.linked_stay and not get_existing_active_stay(doc.name):
        frappe.throw("Boarding stay must exist before check out.", frappe.ValidationError)

    if not doc.actual_check_out_date:
        doc.actual_check_out_date = nowdate()

    validate_boarding_checkout_billing_aligned(doc)

    stay_name = doc.linked_stay or get_existing_active_stay(doc.name)
    if stay_name:
        stay_doc = frappe.get_doc(PET_BOARDING_STAY_DOCTYPE, stay_name)
        if stay_doc.status != "Completed":
            stay_doc.status = "Completed"
            stay_doc.check_out_datetime = now_datetime()
            stay_doc.save(ignore_permissions=True)
        doc.linked_stay = stay_doc.name

    doc.status = "Checked Out"
    doc.save(ignore_permissions=True)
    emit_boarding_event(doc, "boarding_checked_out", extra={"stay": stay_name})
    return {
        "name": doc.name,
        "status": doc.status,
        "stay": stay_name,
        "billable_days": doc.billable_days,
    }
