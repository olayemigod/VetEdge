from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt


BILLING_SESSION_CHARGE_DOCTYPE = "Veterinary Billing Session Charge"
VACCINATION_RECORD_DOCTYPE = "Veterinary Vaccination Record"
CONSULTATION_DOCTYPE = "Veterinary Consultation"


def _vaccination_detail(doc) -> str:
    return str(doc.get("vaccine") or doc.get("name") or "")


def _expected_charge_keys(doc) -> set[str]:
    detail = _vaccination_detail(doc)
    if not doc.get("name") or not detail:
        return set()
    return {
        f"consultation-plan::Vaccination::{doc.name}::{detail}",
        f"Veterinary Vaccination Record:{doc.name}:Vaccination:{detail}",
    }


def _load_vaccination_charge_rows(doc) -> list[dict]:
    if not doc.get("name") or not frappe.db.exists("DocType", BILLING_SESSION_CHARGE_DOCTYPE):
        return []

    fields = [
        "name",
        "parent",
        "source_doctype",
        "source_name",
        "source_detail_name",
        "charge_key",
        "invoice",
        "billing_status",
    ]
    rows: list[dict] = []
    consultation = doc.get("linked_consultation")
    if consultation:
        rows.extend(
            frappe.get_all(
                BILLING_SESSION_CHARGE_DOCTYPE,
                filters={
                    "source_doctype": CONSULTATION_DOCTYPE,
                    "source_name": consultation,
                    "charge_key": ["like", f"consultation-plan::Vaccination::{doc.name}::%"],
                },
                fields=fields,
                order_by="modified desc",
                limit=50,
            )
        )

    rows.extend(
        frappe.get_all(
            BILLING_SESSION_CHARGE_DOCTYPE,
            filters={"source_doctype": VACCINATION_RECORD_DOCTYPE, "source_name": doc.name},
            fields=fields,
            order_by="modified desc",
            limit=50,
        )
    )
    return rows


def _invoice_evidence(invoice_name: str | None) -> dict:
    if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
        return {
            "invoice": invoice_name,
            "docstatus": None,
            "billing_status": "Not Billed",
            "paid_amount": 0.0,
            "outstanding_amount": 0.0,
            "currency": None,
        }

    invoice = frappe.db.get_value(
        "Sales Invoice",
        invoice_name,
        ["docstatus", "status", "grand_total", "paid_amount", "outstanding_amount", "currency"],
        as_dict=True,
    ) or {}
    docstatus = cint(invoice.get("docstatus"))
    paid_amount = flt(invoice.get("paid_amount"))
    outstanding_amount = flt(invoice.get("outstanding_amount"))
    if docstatus == 1:
        from vetedge.services.payment_gate import get_invoice_payment_state

        payment = get_invoice_payment_state(invoice_name) or {}
        paid_amount = flt(payment.get("paid_amount", paid_amount))
        outstanding_amount = flt(payment.get("outstanding_amount", outstanding_amount))
        billing_status = "Paid" if outstanding_amount <= 0 else "Submitted Invoiced"
    elif docstatus == 0:
        billing_status = "Draft Invoiced"
    elif docstatus == 2:
        billing_status = "Cancelled"
    else:
        billing_status = "Not Billed"

    return {
        "invoice": invoice_name,
        "docstatus": docstatus,
        "invoice_status": invoice.get("status"),
        "billing_status": billing_status,
        "grand_total": flt(invoice.get("grand_total")),
        "paid_amount": paid_amount,
        "outstanding_amount": outstanding_amount,
        "currency": invoice.get("currency"),
    }


def _evidence_rank(evidence: dict) -> tuple[int, float]:
    rank = {
        "Paid": 5,
        "Submitted Invoiced": 4,
        "Draft Invoiced": 3,
        "Not Billed": 1,
        "Cancelled": 0,
    }.get(evidence.get("billing_status"), 0)
    return rank, flt(evidence.get("grand_total"))


def get_vaccination_billing_evidence(doc) -> dict:
    """Return invoice evidence for this vaccination charge, not unrelated visit charges."""
    expected_keys = _expected_charge_keys(doc)
    matches = [
        row
        for row in _load_vaccination_charge_rows(doc)
        if str(row.get("charge_key") or "") in expected_keys
    ]
    candidates = []
    for charge in matches:
        evidence = _invoice_evidence(charge.get("invoice"))
        evidence.update(
            {
                "charge_key": charge.get("charge_key"),
                "billing_session": charge.get("parent"),
                "source_detail_name": charge.get("source_detail_name"),
            }
        )
        candidates.append(evidence)

    evidence = max(candidates, key=_evidence_rank) if candidates else _invoice_evidence(None)
    invoice_names = [
        str(candidate.get("invoice"))
        for candidate in candidates
        if candidate.get("invoice") and cint(candidate.get("docstatus")) in {0, 1}
    ]
    return {
        "coverage_complete": cint(evidence.get("docstatus")) in {0, 1},
        "source_invoice_submitted": cint(evidence.get("docstatus")) == 1,
        "evidence": evidence,
        "invoice_names": list(dict.fromkeys(invoice_names)),
        "expected_charge_keys": sorted(expected_keys),
    }


def _standalone_vaccination_gate_mode() -> str:
    from vetedge.services.payment_gate import FULL_PAYMENT_REQUIRED, NO_PAYMENT_GATE
    from vetedge.services.vaccination import is_vaccination_payment_enforcement_enabled

    return FULL_PAYMENT_REQUIRED if is_vaccination_payment_enforcement_enabled() else NO_PAYMENT_GATE


def _legacy_gate_state(doc) -> dict:
    from vetedge.services.payment_gate import evaluate_invoice_payment_gate, get_consultation_payment_gate

    invoice_name = doc.get("linked_invoice")
    if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
        return {
            "can_proceed": False,
            "gate": "Billing Required",
            "status": "Blocked",
            "message": _("Create a Sales Invoice before administering this vaccination."),
            "invoices": [],
        }
    mode = get_consultation_payment_gate() if doc.get("linked_consultation") else _standalone_vaccination_gate_mode()
    state = dict(evaluate_invoice_payment_gate(invoice_name, mode, "vaccination") or {})
    state["invoices"] = [_invoice_evidence(invoice_name)]
    return state


def get_vaccination_administration_gate_state(doc) -> dict:
    """Return the complete billing/payment decision for vaccination administration.

    A billable vaccination must first prove that *its own charge* is represented
    by a submitted Sales Invoice. Only then is the configured payment policy
    evaluated. Elevated roles do not bypass this accounting/clinical invariant.
    """
    if not doc.get("billing_item"):
        return {
            "can_proceed": False,
            "gate": "Billing Required",
            "status": "Blocked",
            "message": _("Configure the vaccine ERPNext billing Item before administration."),
            "billing_context": "consultation" if doc.get("linked_consultation") else "standalone_vaccination",
        }

    from vetedge.services.vaccination import use_billing_core_for_vaccination

    if not use_billing_core_for_vaccination():
        state = _legacy_gate_state(doc)
        state["billing_context"] = "consultation" if doc.get("linked_consultation") else "standalone_vaccination"
        return state

    evidence = get_vaccination_billing_evidence(doc)
    context = "consultation" if doc.get("linked_consultation") else "standalone_vaccination"
    if not evidence.get("coverage_complete"):
        return {
            "can_proceed": False,
            "gate": "Billing Required",
            "status": "Blocked",
            "message": _("Create or update the invoice so this vaccination charge is billed before administration."),
            "billing_context": context,
            "vaccination_charge_coverage_complete": False,
            "vaccination_invoice_names": evidence.get("invoice_names") or [],
            "vaccination_billing_evidence": evidence.get("evidence") or {},
        }
    if not evidence.get("source_invoice_submitted"):
        return {
            "can_proceed": False,
            "gate": "Submitted Invoice Required",
            "status": "Blocked",
            "message": _("Submit the Sales Invoice containing this vaccination charge before administration."),
            "billing_context": context,
            "vaccination_charge_coverage_complete": True,
            "vaccination_invoice_names": evidence.get("invoice_names") or [],
            "vaccination_billing_evidence": evidence.get("evidence") or {},
        }

    if doc.get("linked_consultation"):
        from vetedge.services.clinical_payment_gate import get_strict_source_payment_gate_status

        state = dict(
            get_strict_source_payment_gate_status(
                CONSULTATION_DOCTYPE,
                doc.get("linked_consultation"),
            )
            or {}
        )
    else:
        from vetedge.services.billing_core import get_invoice_collection_payment_gate_status

        state = dict(
            get_invoice_collection_payment_gate_status(
                evidence.get("invoice_names") or [],
                _standalone_vaccination_gate_mode(),
            )
            or {}
        )

    state.setdefault("gate", "Payment Gate")
    state.setdefault("status", "Allowed" if state.get("can_proceed") else "Blocked")
    state["billing_context"] = context
    state["vaccination_charge_coverage_complete"] = True
    state["vaccination_invoice_names"] = evidence.get("invoice_names") or []
    state["vaccination_billing_evidence"] = evidence.get("evidence") or {}
    if not state.get("can_proceed") and not state.get("message"):
        state["message"] = _("Complete the required Billing & Payment step before administering this vaccination.")
    return state


def enforce_vaccination_payment_before_administration(doc, user: str | None = None) -> None:
    """Server-side vaccination gate. ``user`` is accepted for API compatibility only."""
    del user
    state = get_vaccination_administration_gate_state(doc)
    if state.get("can_proceed"):
        return
    frappe.throw(
        state.get("message")
        or _("Complete the required Billing & Payment step before administering this vaccination."),
        frappe.ValidationError,
    )
