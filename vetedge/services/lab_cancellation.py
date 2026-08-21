from __future__ import annotations

from collections import OrderedDict

import frappe
from frappe import _
from frappe.utils import cint, flt

from vetedge.services.portal_access import require_internal_user


LAB_ORDER_DOCTYPE = "Veterinary Lab Order"
BILLING_SESSION_DOCTYPE = "Veterinary Billing Session"
BILLING_SESSION_CHARGE_DOCTYPE = "Veterinary Billing Session Charge"

RESULT_EVIDENCE_FIELDS = (
    "result_value",
    "result_text",
    "result_attachment",
    "remarks",
)
RESULT_EVIDENCE_ORDER_STATUSES = {
    "Result Entered",
    "Awaiting Review",
    "Reviewed",
    "Completed",
}
RESULT_EVIDENCE_ROW_STATUSES = {
    "Result Entered",
    "Awaiting Review",
    "Reviewed",
    "Completed",
}
RESULT_EVIDENCE_RESULT_STATUSES = {
    "Entered",
    "Awaiting Review",
    "Reviewed",
}

PROTECTED_PLAN_BILLING_STATUSES = {
    "Draft Invoiced",
    "Submitted Invoiced",
    "Paid",
}
PROTECTED_PLAN_PAYMENT_STATUSES = {
    "Unpaid",
    "Partly Paid",
    "Paid",
}


def _previous_doc(doc):
    getter = getattr(doc, "get_doc_before_save", None)
    return getter() if callable(getter) else None


def _source_doc_for_evidence(doc):
    return _previous_doc(doc) or doc


def _has_result_evidence(doc) -> bool:
    source = _source_doc_for_evidence(doc)
    if source.get("status") in RESULT_EVIDENCE_ORDER_STATUSES:
        return True

    for row in source.get("lab_tests") or []:
        if row.get("status") in RESULT_EVIDENCE_ROW_STATUSES:
            return True
        if row.get("result_status") in RESULT_EVIDENCE_RESULT_STATUSES:
            return True
        if any(row.get(fieldname) not in (None, "") for fieldname in RESULT_EVIDENCE_FIELDS):
            return True
    return False


def _get_consultation_plan_rows(doc) -> list:
    source = _source_doc_for_evidence(doc)
    consultation_name = source.get("consultation")
    if not consultation_name or not frappe.db.exists("Veterinary Consultation", consultation_name):
        return []

    consultation = frappe.get_doc("Veterinary Consultation", consultation_name)
    return [
        row
        for row in consultation.get("planned_treatments") or []
        if row.get("source_type") == "Lab Order" and row.get("source_document") == source.name
    ]


def _invoice_state(invoice_name: str) -> dict:
    if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
        return {
            "invoice": invoice_name,
            "docstatus": None,
            "status": None,
            "grand_total": 0.0,
            "paid_amount": 0.0,
            "outstanding_amount": 0.0,
            "payment_state": "Missing",
        }

    invoice = frappe.db.get_value(
        "Sales Invoice",
        invoice_name,
        ["docstatus", "status", "grand_total", "paid_amount", "outstanding_amount"],
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

    if docstatus == 0:
        payment_state = "Draft"
    elif docstatus == 2:
        payment_state = "Cancelled"
    elif docstatus == 1 and outstanding_amount <= 0:
        payment_state = "Paid"
    elif docstatus == 1 and (paid_amount > 0 or (grand_total and outstanding_amount < grand_total)):
        payment_state = "Partly Paid"
    elif docstatus == 1:
        payment_state = "Unpaid"
    else:
        payment_state = "Missing"

    return {
        "invoice": invoice_name,
        "docstatus": docstatus,
        "status": invoice.get("status"),
        "grand_total": grand_total,
        "paid_amount": paid_amount,
        "outstanding_amount": outstanding_amount,
        "payment_state": payment_state,
    }


def _collect_invoice_evidence(doc) -> list[dict]:
    source = _source_doc_for_evidence(doc)
    invoice_names: OrderedDict[str, None] = OrderedDict()

    linked_invoice = source.get("linked_invoice")
    if linked_invoice:
        invoice_names[linked_invoice] = None

    try:
        from vetedge.services.lab_billing_context import get_lab_billing_evidence

        evidence = get_lab_billing_evidence(source) or {}
        for invoice_name in evidence.get("invoice_names") or []:
            if invoice_name:
                invoice_names[invoice_name] = None
        for row_evidence in (evidence.get("row_billing") or {}).values():
            invoice_name = row_evidence.get("invoice") if row_evidence else None
            if invoice_name:
                invoice_names[invoice_name] = None
    except Exception:
        pass

    return [_invoice_state(name) for name in invoice_names]


def _build_financial_blockers(doc, invoice_evidence: list[dict], plan_rows: list) -> list[str]:
    blockers: list[str] = []

    submitted = [row for row in invoice_evidence if cint(row.get("docstatus")) == 1]
    if submitted:
        names = ", ".join(row.get("invoice") for row in submitted if row.get("invoice"))
        paid = any(row.get("payment_state") in {"Paid", "Partly Paid"} for row in submitted)
        if paid:
            blockers.append(
                _(
                    "This Lab Order has submitted invoice/payment evidence ({0}). "
                    "Record an approved financial cancellation resolution before cancelling it."
                ).format(names)
            )
        else:
            blockers.append(
                _(
                    "This Lab Order is already on a submitted Sales Invoice ({0}). "
                    "Resolve the accounting treatment before cancelling it."
                ).format(names)
            )

    drafts = [row for row in invoice_evidence if cint(row.get("docstatus")) == 0]
    if drafts:
        names = ", ".join(row.get("invoice") for row in drafts if row.get("invoice"))
        blockers.append(
            _(
                "This Lab Order is linked to draft billing ({0}). "
                "Remove or reconcile the draft billing first, then retry cancellation."
            ).format(names)
        )

    protected_plan_rows = [
        row
        for row in plan_rows
        if row.get("billing_status") in PROTECTED_PLAN_BILLING_STATUSES
        or row.get("payment_status") in PROTECTED_PLAN_PAYMENT_STATUSES
    ]
    if protected_plan_rows and not submitted and not drafts:
        billing_states = ", ".join(
            sorted(
                {
                    str(row.get("billing_status") or row.get("payment_status"))
                    for row in protected_plan_rows
                    if row.get("billing_status") or row.get("payment_status")
                }
            )
        )
        blockers.append(
            _(
                "Consultation billing for this Lab Order is already financially committed ({0}). "
                "Resolve the billing state before cancellation."
            ).format(billing_states or _("billing exists"))
        )

    return blockers


def build_lab_order_cancellation_preflight(doc) -> dict:
    invoice_evidence = _collect_invoice_evidence(doc)
    plan_rows = _get_consultation_plan_rows(doc)
    blockers = _build_financial_blockers(doc, invoice_evidence, plan_rows)
    has_result_evidence = _has_result_evidence(doc)

    if has_result_evidence:
        blockers.insert(
            0,
            _(
                "This Lab Order already contains entered, reviewed, or completed diagnostic result evidence. "
                "Use a controlled clinical correction/void process instead of ordinary cancellation."
            ),
        )

    return {
        "can_cancel": not blockers,
        "message": " ".join(blockers),
        "blockers": blockers,
        "has_result_evidence": has_result_evidence,
        "invoice_evidence": invoice_evidence,
        "consultation_plan_rows": [
            {
                "name": row.get("name"),
                "billing_status": row.get("billing_status"),
                "payment_status": row.get("payment_status"),
                "source_detail_name": row.get("source_detail_name"),
            }
            for row in plan_rows
        ],
    }


@frappe.whitelist()
def get_lab_order_cancellation_preflight(lab_order: str) -> dict:
    require_internal_user()
    from vetedge.services.permissions import can_access_lab_order

    can_access_lab_order(frappe.session.user, lab_order, raise_exception=True)
    if not frappe.db.exists(LAB_ORDER_DOCTYPE, lab_order):
        frappe.throw(_("The selected Lab Order could not be found."), frappe.DoesNotExistError)
    return build_lab_order_cancellation_preflight(frappe.get_doc(LAB_ORDER_DOCTYPE, lab_order))


def _remove_safe_consultation_plan_rows(doc) -> int:
    source = _source_doc_for_evidence(doc)
    consultation_name = source.get("consultation")
    if not consultation_name or not frappe.db.exists("Veterinary Consultation", consultation_name):
        return 0

    consultation = frappe.get_doc("Veterinary Consultation", consultation_name)
    matching = [
        row
        for row in consultation.get("planned_treatments") or []
        if row.get("source_type") == "Lab Order" and row.get("source_document") == source.name
    ]
    if not matching:
        return 0

    protected = [
        row
        for row in matching
        if row.get("billing_status") in PROTECTED_PLAN_BILLING_STATUSES
        or row.get("payment_status") in PROTECTED_PLAN_PAYMENT_STATUSES
    ]
    if protected:
        frappe.throw(
            _("Lab cancellation cannot remove financially committed Consultation treatment rows."),
            frappe.ValidationError,
        )

    remaining = [
        row
        for row in consultation.get("planned_treatments") or []
        if not (row.get("source_type") == "Lab Order" and row.get("source_document") == source.name)
    ]
    consultation.set("planned_treatments", remaining)

    from vetedge.services.consultation_billing_plan import _save_consultation

    _save_consultation(consultation)
    return len(matching)


def _find_uninvoiced_charge_rows(doc) -> list[dict]:
    if not frappe.db.exists("DocType", BILLING_SESSION_CHARGE_DOCTYPE):
        return []

    source = _source_doc_for_evidence(doc)
    fields = [
        "name",
        "parent",
        "source_doctype",
        "source_name",
        "charge_key",
        "invoice",
        "billing_status",
        "notes",
    ]
    rows = frappe.get_all(
        BILLING_SESSION_CHARGE_DOCTYPE,
        filters={"source_doctype": LAB_ORDER_DOCTYPE, "source_name": source.name},
        fields=fields,
        limit=200,
    )

    consultation_name = source.get("consultation")
    if consultation_name:
        rows.extend(
            frappe.get_all(
                BILLING_SESSION_CHARGE_DOCTYPE,
                filters={
                    "source_doctype": "Veterinary Consultation",
                    "source_name": consultation_name,
                    "charge_key": ["like", f"consultation-plan::Lab Order::{source.name}::%"],
                },
                fields=fields,
                limit=200,
            )
        )

    deduped: OrderedDict[str, dict] = OrderedDict()
    for row in rows:
        if row.get("name"):
            deduped[row.name] = row
    return list(deduped.values())


def _retire_uninvoiced_charge_rows(doc) -> int:
    rows = _find_uninvoiced_charge_rows(doc)
    if not rows:
        return 0

    retired = 0
    sessions: set[str] = set()
    for row in rows:
        invoice_name = row.get("invoice")
        if invoice_name and frappe.db.exists("Sales Invoice", invoice_name):
            docstatus = cint(frappe.db.get_value("Sales Invoice", invoice_name, "docstatus"))
            if docstatus in {0, 1}:
                frappe.throw(
                    _("Lab cancellation cannot retire a charge linked to an active Sales Invoice."),
                    frappe.ValidationError,
                )

        if row.get("billing_status") in {"Submitted Invoiced", "Paid"}:
            frappe.throw(
                _("Lab cancellation cannot retire submitted or paid billing charges."),
                frappe.ValidationError,
            )

        sessions.add(row.get("parent"))
        if row.get("billing_status") in {"Cancelled", "Skipped"}:
            continue

        note = _("Retired because Lab Order {0} was cancelled before invoice commitment.").format(doc.name)
        notes = "; ".join(part for part in [row.get("notes"), note] if part)
        frappe.db.set_value(
            BILLING_SESSION_CHARGE_DOCTYPE,
            row.name,
            {"billing_status": "Cancelled", "notes": notes},
            update_modified=False,
        )
        retired += 1

    if sessions and frappe.db.exists("DocType", BILLING_SESSION_DOCTYPE):
        from vetedge.services.billing_core import refresh_billing_session_totals

        for session_name in sorted(name for name in sessions if name):
            if not frappe.db.exists(BILLING_SESSION_DOCTYPE, session_name):
                continue
            session = frappe.get_doc(BILLING_SESSION_DOCTYPE, session_name)
            refresh_billing_session_totals(session)
            session.save(ignore_permissions=True)

    return retired


def _cleanup_safe_uncommitted_billing(doc) -> dict:
    return {
        "removed_consultation_plan_rows": _remove_safe_consultation_plan_rows(doc),
        "retired_uninvoiced_charges": _retire_uninvoiced_charge_rows(doc),
    }


def enforce_lab_order_cancellation(doc) -> None:
    if doc.get("status") != "Cancelled":
        return

    previous = _previous_doc(doc)
    if not previous:
        frappe.throw(_("A new Lab Order cannot be created directly as Cancelled."), frappe.ValidationError)
    if previous.get("status") == "Cancelled":
        return

    preflight = build_lab_order_cancellation_preflight(doc)
    if not preflight.get("can_cancel"):
        frappe.throw(
            preflight.get("message") or _("This Lab Order cannot be cancelled safely."),
            frappe.ValidationError,
        )

    _cleanup_safe_uncommitted_billing(doc)


def enforce_lab_order_delete(doc) -> None:
    if cint(doc.get("docstatus")) != 0:
        frappe.throw(_("Submitted or cancelled Lab Order documents cannot be deleted."), frappe.ValidationError)
    if doc.get("status") not in {"Draft", "Ordered"}:
        frappe.throw(
            _("Only Draft or Ordered Lab Orders without clinical result history can be deleted."),
            frappe.ValidationError,
        )

    preflight = build_lab_order_cancellation_preflight(doc)
    if not preflight.get("can_cancel"):
        frappe.throw(
            preflight.get("message") or _("This Lab Order cannot be deleted safely."),
            frappe.ValidationError,
        )

    _cleanup_safe_uncommitted_billing(doc)
