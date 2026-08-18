from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt


BILLING_SESSION_CHARGE_DOCTYPE = "Veterinary Billing Session Charge"
LAB_ORDER_DOCTYPE = "Veterinary Lab Order"
CONSULTATION_DOCTYPE = "Veterinary Consultation"


def _active_billable_rows(doc) -> list:
    return [
        row
        for row in doc.get("lab_tests") or []
        if row.get("status") != "Cancelled" and row.get("billing_item")
    ]


def _row_details(row) -> list[str]:
    values = [row.get("name"), row.get("lab_test_template")]
    return list(dict.fromkeys(str(value) for value in values if value))


def _expected_charge_keys(doc, row) -> set[str]:
    keys: set[str] = set()
    for detail in _row_details(row):
        keys.update(
            {
                f"consultation-plan::Lab Order::{doc.name}::{detail}",
                f"Veterinary Lab Order:{doc.name}:Lab:{detail}",
                f"Veterinary Lab Order:{doc.name}:Lab Order:{detail}",
            }
        )
    return keys


def _load_lab_charge_rows(doc) -> list[dict]:
    if not frappe.db.exists("DocType", BILLING_SESSION_CHARGE_DOCTYPE):
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
    consultation = doc.get("consultation")
    if consultation:
        rows.extend(
            frappe.get_all(
                BILLING_SESSION_CHARGE_DOCTYPE,
                filters={
                    "source_doctype": CONSULTATION_DOCTYPE,
                    "source_name": consultation,
                    "charge_key": ["like", f"consultation-plan::Lab Order::{doc.name}::%"],
                },
                fields=fields,
                order_by="modified desc",
                limit=200,
            )
        )

    rows.extend(
        frappe.get_all(
            BILLING_SESSION_CHARGE_DOCTYPE,
            filters={"source_doctype": LAB_ORDER_DOCTYPE, "source_name": doc.name},
            fields=fields,
            order_by="modified desc",
            limit=200,
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
    grand_total = flt(invoice.get("grand_total"))
    paid_amount = flt(invoice.get("paid_amount"))
    outstanding_amount = flt(invoice.get("outstanding_amount"))

    if docstatus == 1:
        try:
            from vetedge.services.payment_gate import get_invoice_payment_state

            payment = get_invoice_payment_state(invoice_name) or {}
            paid_amount = flt(payment.get("paid_amount", paid_amount))
            outstanding_amount = flt(payment.get("outstanding_amount", outstanding_amount))
        except Exception:
            pass
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
        "grand_total": grand_total,
        "paid_amount": paid_amount,
        "outstanding_amount": outstanding_amount,
        "currency": invoice.get("currency"),
    }


def _evidence_rank(evidence: dict) -> tuple[int, float]:
    status = evidence.get("billing_status")
    rank = {
        "Paid": 5,
        "Submitted Invoiced": 4,
        "Draft Invoiced": 3,
        "Not Billed": 1,
        "Cancelled": 0,
    }.get(status, 0)
    return rank, flt(evidence.get("grand_total"))


def get_lab_billing_evidence(doc) -> dict:
    """Read Lab-specific billing evidence without creating or mutating billing records."""
    rows = _active_billable_rows(doc)
    charges = _load_lab_charge_rows(doc)
    row_billing: dict[str, dict] = {}
    missing_rows: list[str] = []
    invoice_names: list[str] = []

    for row in rows:
        expected_keys = _expected_charge_keys(doc, row)
        matches = [charge for charge in charges if str(charge.get("charge_key") or "") in expected_keys]
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
        row_key = str(row.get("name") or row.get("lab_test_template") or "")
        if row_key:
            row_billing[row_key] = evidence
        if row.get("lab_test_template"):
            row_billing.setdefault(str(row.get("lab_test_template")), evidence)

        if evidence.get("docstatus") not in {0, 1}:
            missing_rows.append(row.get("lab_test_name") or row.get("lab_test_template") or row_key)
        if evidence.get("invoice") and evidence.get("docstatus") in {0, 1}:
            if evidence["invoice"] not in invoice_names:
                invoice_names.append(evidence["invoice"])

    return {
        "coverage_complete": bool(rows) and not missing_rows,
        "row_billing": row_billing,
        "missing_rows": missing_rows,
        "invoice_names": invoice_names,
    }


def get_lab_billing_core_gate_state(doc) -> dict:
    """Evaluate Lab workflow billing against its real accounting context.

    Consultation-linked Lab Orders are billed as Consultation treatment-plan
    charges. Every Lab Test must first have matching invoice evidence; only then
    can the Consultation payment gate satisfy the Lab workflow. Standalone Lab
    Orders retain their own Billing Core source/gate behaviour.
    """
    evidence = get_lab_billing_evidence(doc)
    consultation = doc.get("consultation")

    if not evidence.get("coverage_complete"):
        missing = ", ".join(str(value) for value in evidence.get("missing_rows") or [] if value)
        if consultation:
            message = _(
                "Create or update the Consultation invoice so every Lab Test is billed before laboratory processing can begin."
            )
        else:
            message = _("Create the Lab Order invoice before laboratory processing can begin.")
        if missing:
            message = f"{message} {_('Not yet invoiced')}: {missing}."
        return {
            "can_proceed": False,
            "billable": True,
            "gate": "Billing Required",
            "message": message,
            "billing_context": "consultation" if consultation else "standalone_lab",
            "row_billing": evidence.get("row_billing") or {},
            "lab_charge_coverage_complete": False,
            "lab_invoice_names": evidence.get("invoice_names") or [],
        }

    from vetedge.services.billing_core import get_source_payment_gate_status

    if consultation:
        state = dict(get_source_payment_gate_status(CONSULTATION_DOCTYPE, consultation) or {})
        context = "consultation"
    else:
        state = dict(get_source_payment_gate_status(LAB_ORDER_DOCTYPE, doc.name) or {})
        context = "standalone_lab"

    state.setdefault("billable", True)
    state.setdefault("gate", "Payment Gate")
    state["billing_context"] = context
    state["row_billing"] = evidence.get("row_billing") or {}
    state["lab_charge_coverage_complete"] = True
    state["lab_invoice_names"] = evidence.get("invoice_names") or []
    if not state.get("can_proceed") and not state.get("message"):
        state["message"] = _(
            "Complete the required Billing & Payment step before laboratory processing can continue."
        )
    return state
