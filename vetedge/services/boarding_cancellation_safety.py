from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from vetedge.services.permissions import can_access_branch_data, get_current_user
from vetedge.services.platform_access import require_vetedge_platform_access

INACTIVE_BOARDING_CHARGE_STATUSES = {"Cancelled", "Skipped"}


def get_boarding_cancellation_state(doc) -> dict:
    """Return whether a Boarding Booking may be clinically cancelled.

    Boarding cancellation is intentionally conservative until its dedicated
    financial-correction flow can reconcile active billing. Cancelled invoices
    and retired charges are historical evidence and do not block; any pending
    charge or active Draft/Submitted invoice does.
    """
    from vetedge.services.boarding import get_boarding_invoice_documents

    active_invoices = {
        invoice.name
        for invoice in get_boarding_invoice_documents(doc)
        if cint(getattr(invoice, "docstatus", 0)) != 2
    }
    pending_charge = False

    if doc.get("name") and frappe.db.exists("DocType", "Veterinary Billing Session Charge"):
        rows = frappe.get_all(
            "Veterinary Billing Session Charge",
            filters={"source_doctype": "Pet Boarding Booking", "source_name": doc.name},
            fields=["invoice", "billing_status"],
            limit=100,
        )
        for row in rows:
            if row.get("billing_status") in INACTIVE_BOARDING_CHARGE_STATUSES:
                continue
            invoice_name = row.get("invoice")
            if not invoice_name:
                pending_charge = True
                continue
            if not frappe.db.exists("Sales Invoice", invoice_name):
                pending_charge = True
                continue
            if cint(frappe.db.get_value("Sales Invoice", invoice_name, "docstatus")) != 2:
                active_invoices.add(invoice_name)

    can_cancel = not pending_charge and not active_invoices
    return {
        "can_cancel": can_cancel,
        "pending_charge": pending_charge,
        "active_invoices": sorted(active_invoices),
        "message": (
            _("Boarding Booking may be cancelled because it has no active billing history.")
            if can_cancel
            else _(
                "This Boarding Booking already has active billing. Resolve or cancel Draft/Unpaid billing first; paid or partly-paid invoices require the appropriate financial correction before the booking can be cancelled."
            )
        ),
    }


def enforce_boarding_cancellation_safety(doc) -> None:
    previous = doc.get_doc_before_save() if getattr(doc, "get_doc_before_save", None) else None
    if not previous or previous.get("status") == doc.get("status") or doc.get("status") != "Cancelled":
        return

    require_vetedge_platform_access(
        action="cancel_boarding_booking",
        reference_doctype="Pet Boarding Booking",
        reference_name=doc.name,
    )
    if not doc.has_permission("write"):
        frappe.throw(_("You are not permitted to cancel this Boarding Booking."), frappe.PermissionError)
    if doc.get("service_branch"):
        can_access_branch_data(get_current_user(), doc.service_branch, raise_exception=True)

    state = get_boarding_cancellation_state(doc)
    if not state.get("can_cancel"):
        frappe.throw(state.get("message"), frappe.ValidationError)
