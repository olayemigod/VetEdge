from __future__ import annotations

from frappe.utils import cint


def get_strict_source_payment_gate_status(source_doctype: str, source_name: str) -> dict:
    """Evaluate a Billing Core source gate without allowing active draft work to hide behind history.

    ``get_source_payment_gate_status`` deliberately reconciles active and historical
    invoice evidence. Clinical service progression needs one additional invariant:
    an *active* billing cycle with pending charges or a Draft Sales Invoice is never
    ready for service, even when an older submitted/paid invoice also exists.
    """
    from vetedge.services.billing_core import (
        get_billing_session_invoice_ledger,
        get_source_payment_gate_mode,
        get_source_payment_gate_status,
        normalize_payment_gate_mode,
        resolve_billing_session,
    )

    mode = normalize_payment_gate_mode(get_source_payment_gate_mode(source_doctype))
    active_session = resolve_billing_session(source_doctype, source_name)
    if active_session:
        ledger = get_billing_session_invoice_ledger(active_session)
        invoices = ledger.get("invoices") or []
        if ledger.get("has_pending_uninvoiced_charges"):
            return {
                "gate": mode,
                "can_proceed": False,
                "status": "Blocked",
                "message": "A Sales Invoice must be generated for pending charges before this clinical service can proceed.",
                "invoices": invoices,
            }
        if ledger.get("has_active_draft_invoice"):
            return {
                "gate": mode,
                "can_proceed": False,
                "status": "Blocked",
                "message": "Please submit the active Sales Invoice before this clinical service can proceed.",
                "invoices": invoices,
            }
        if invoices and not any(cint(row.get("docstatus")) == 1 for row in invoices):
            return {
                "gate": mode,
                "can_proceed": False,
                "status": "Blocked",
                "message": "Please submit the Sales Invoice before this clinical service can proceed.",
                "invoices": invoices,
            }

    return dict(get_source_payment_gate_status(source_doctype, source_name) or {})
