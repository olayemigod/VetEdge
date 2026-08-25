from __future__ import annotations

import frappe
from frappe.utils import now_datetime, nowdate

from vetedge.services import boarding
from vetedge.services.boarding_billing_release_safety import validate_boarding_checkout_release_safety
from vetedge.services.portal_access import require_internal_user


@frappe.whitelist()
def check_out_boarding_booking(booking: str) -> dict:
    """Release-safe Boarding checkout using cumulative invoice reconciliation.

    This intentionally bypasses the legacy pre-check in boarding.py for PR #36.
    The legacy pre-check only sees the current direct Boarding invoice references,
    while this adapter also reconciles explicit historical Boarding Billing Session
    invoices before allowing the operational stay to complete.
    """
    require_internal_user()
    boarding.ensure_boarding_enabled()

    from vetedge.services.platform_access import require_vetedge_platform_access

    require_vetedge_platform_access(
        action="check_out_boarding_booking",
        reference_doctype=boarding.PET_BOARDING_BOOKING_DOCTYPE,
        reference_name=booking,
    )

    doc = frappe.get_doc(boarding.PET_BOARDING_BOOKING_DOCTYPE, booking)
    boarding.ensure_booking_transition_allowed(doc.status, "Checked Out")

    if not doc.linked_stay and not boarding.get_existing_active_stay(doc.name):
        frappe.throw("Boarding stay must exist before check out.", frappe.ValidationError)

    if not doc.actual_check_out_date:
        doc.actual_check_out_date = nowdate()

    # Accounting invariant: all current Boarding charges must be represented by
    # explicit active Boarding invoices and all submitted invoices must be paid.
    # Submitted Sales Invoices are never mutated here.
    validate_boarding_checkout_release_safety(doc)

    stay_name = doc.linked_stay or boarding.get_existing_active_stay(doc.name)
    if stay_name:
        stay_doc = frappe.get_doc(boarding.PET_BOARDING_STAY_DOCTYPE, stay_name)
        if stay_doc.status != "Completed":
            stay_doc.status = "Completed"
            stay_doc.check_out_datetime = now_datetime()
            stay_doc.save(ignore_permissions=True)
        doc.linked_stay = stay_doc.name

    doc.status = "Checked Out"
    doc.save(ignore_permissions=True)
    boarding.emit_boarding_event(doc, "boarding_checked_out", extra={"stay": stay_name})

    return {
        "name": doc.name,
        "status": doc.status,
        "stay": stay_name,
        "billable_days": doc.billable_days,
    }
