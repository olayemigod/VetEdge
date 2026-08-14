from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt

from vetedge.services.portal_access import require_internal_user


GROOMING_PROGRESS_STATUSES = {"In Progress", "Completed"}


def get_grooming_service_payment_gate_state(doc) -> dict:
    from vetedge.services.grooming import is_grooming_billing_enabled, use_billing_core_for_grooming

    if not is_grooming_billing_enabled():
        return {
            "can_proceed": True,
            "billable": False,
            "gate": "Grooming Billing Disabled",
            "message": _("Grooming billing is disabled, so payment does not block service."),
        }

    if use_billing_core_for_grooming() and doc.get("name"):
        from vetedge.services.billing_core import get_billing_session_summary, resolve_billing_session

        session = resolve_billing_session("Pet Grooming Session", doc.name, include_closed_satisfied=True)
        if not session:
            return {
                "can_proceed": False,
                "billable": True,
                "gate": "Billing Required",
                "message": _("Create the Grooming invoice in Billing / Payment before grooming can start."),
            }
        summary = get_billing_session_summary(session)
        invoices = [row for row in summary.get("invoices") or [] if cint(row.get("docstatus")) != 2]
        pending_charges = [
            row
            for row in summary.get("charges") or []
            if not row.get("invoice") or row.get("billing_status") in {"Pending", "Draft Invoiced"}
        ]
        has_draft = any(cint(row.get("docstatus")) == 0 for row in invoices)
        outstanding = flt(summary.get("outstanding_amount"))
        can_proceed = bool(invoices and not pending_charges and not has_draft and outstanding <= 0)
        return {
            "can_proceed": can_proceed,
            "billable": True,
            "gate": "Full Grooming Payment",
            "message": (
                _("Grooming billing is fully paid.")
                if can_proceed
                else _("Submit and fully pay the Grooming invoice before grooming can start or complete.")
            ),
        }

    invoice_name = doc.get("linked_invoice")
    if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
        return {
            "can_proceed": False,
            "billable": True,
            "gate": "Billing Required",
            "message": _("Create the Grooming invoice before grooming can start."),
        }
    invoice = frappe.db.get_value(
        "Sales Invoice",
        invoice_name,
        ["docstatus", "outstanding_amount"],
        as_dict=True,
    )
    can_proceed = bool(invoice and cint(invoice.get("docstatus")) == 1 and flt(invoice.get("outstanding_amount")) <= 0)
    return {
        "can_proceed": can_proceed,
        "billable": True,
        "gate": "Full Grooming Payment",
        "message": (
            _("Grooming invoice is fully paid.")
            if can_proceed
            else _("Submit and fully pay the Grooming invoice before grooming can start or complete.")
        ),
    }


def enforce_grooming_service_payment_gate(doc, method: str | None = None) -> None:
    previous = doc.get_doc_before_save() if getattr(doc, "get_doc_before_save", None) else None
    if not previous or doc.get("status") == previous.get("status"):
        return
    if doc.get("status") not in GROOMING_PROGRESS_STATUSES:
        return
    state = get_grooming_service_payment_gate_state(doc)
    if state.get("can_proceed"):
        return
    frappe.throw(state.get("message") or _("Complete Grooming Billing / Payment before service can proceed."), frappe.ValidationError)


@frappe.whitelist()
def transition_grooming_session_status(session: str, status: str) -> dict:
    require_internal_user()
    from vetedge.services.grooming import transition_grooming_session_status as original
    from vetedge.services.platform_access import require_vetedge_platform_access

    require_vetedge_platform_access(
        action="transition_grooming_session_status",
        reference_doctype="Pet Grooming Session",
        reference_name=session,
    )
    return original(session=session, status=status)
