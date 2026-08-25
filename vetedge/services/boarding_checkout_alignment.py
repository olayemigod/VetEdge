from __future__ import annotations

import frappe
from frappe.utils import now_datetime, nowdate

from vetedge.services.boarding import (
    PET_BOARDING_BOOKING_DOCTYPE,
    PET_BOARDING_STAY_DOCTYPE,
    emit_boarding_event,
    ensure_booking_transition_allowed,
    get_existing_active_stay,
)
from vetedge.services.boarding_billing_release_safety import validate_boarding_checkout_release_safety


def validate_boarding_checkout_billing_aligned(doc) -> None:
    """Validate Boarding checkout against cumulative explicit invoice evidence.

    PR #36 release safety intentionally does not resync Boarding into the generic
    Billing Session charge engine here. Boarding charges are duration-based and
    can change after a submitted invoice; resyncing the changed cumulative total
    as a new Billing Session charge can duplicate the full stay amount.

    The release-safety reconciler instead treats submitted Boarding invoices as
    immutable historical billing, adds any Boarding adjustment invoices, and
    requires their cumulative active total to equal the current stay charge.
    """
    validate_boarding_checkout_release_safety(doc)


def check_out_boarding_booking_doc_aligned(doc) -> dict:
    """Checkout only after cumulative Boarding billing is reconciled and paid."""
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
