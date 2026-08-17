from __future__ import annotations

import frappe
from frappe.utils import cint, getdate, nowdate

from vetedge.services.portal_access import require_internal_user


def _invoice_names(rows: list[dict] | None) -> set[str]:
    return {
        str(row.get("name") or row.get("invoice") or "").strip()
        for row in rows or []
        if str(row.get("name") or row.get("invoice") or "").strip()
    }


def _patient_map(invoice_names: set[str], customer: str | None) -> dict[str, str]:
    if not invoice_names or not frappe.db.exists("DocType", "Veterinary Billing Session"):
        return {}

    names = list(invoice_names)
    session_filters = {"customer": customer} if customer else {}
    sessions = frappe.get_all(
        "Veterinary Billing Session",
        filters=session_filters,
        or_filters=[
            ["Veterinary Billing Session", "current_draft_invoice", "in", names],
            ["Veterinary Billing Session", "latest_invoice", "in", names],
        ],
        fields=["name", "animal", "current_draft_invoice", "latest_invoice"],
        limit_page_length=max(len(names) * 2, 20),
    )
    mapped: dict[str, str] = {}
    for row in sessions:
        patient = str(row.get("animal") or "")
        if not patient:
            continue
        for fieldname in ("current_draft_invoice", "latest_invoice"):
            invoice = str(row.get(fieldname) or "")
            if invoice in invoice_names:
                mapped[invoice] = patient

    unresolved = invoice_names - set(mapped)
    if unresolved and frappe.db.exists("DocType", "Veterinary Billing Session Charge"):
        charges = frappe.get_all(
            "Veterinary Billing Session Charge",
            filters={"invoice": ["in", list(unresolved)]},
            fields=["invoice", "parent", "source_doctype", "source_name"],
            limit_page_length=max(len(unresolved) * 10, 50),
        )
        parents = list({str(row.get("parent") or "") for row in charges if row.get("parent")})
        patient_by_session: dict[str, str] = {}
        if parents:
            parent_filters: dict = {"name": ["in", parents]}
            if customer:
                parent_filters["customer"] = customer
            patient_by_session = {
                row.name: str(row.get("animal") or "")
                for row in frappe.get_all(
                    "Veterinary Billing Session",
                    filters=parent_filters,
                    fields=["name", "animal"],
                    limit_page_length=len(parents),
                )
            }
        for charge in charges:
            invoice = str(charge.get("invoice") or "")
            patient = patient_by_session.get(str(charge.get("parent") or ""), "")
            if not patient and charge.get("source_doctype") == "Veterinary Patient":
                patient = str(charge.get("source_name") or "")
            if invoice and patient:
                mapped[invoice] = patient
    return mapped


def _enrich_owner_outstanding(state: dict) -> dict:
    rows = state.get("patient_outstanding_context") or []
    if not rows:
        state["outstanding_context_scope"] = "owner"
        return state

    source = state.get("source") or {}
    customer = source.get("owner") or source.get("customer")
    names = _invoice_names(rows)
    patients = _patient_map(names, customer)
    patient_names: dict[str, str] = {}
    ids = list({patient for patient in patients.values() if patient})
    if ids:
        patient_names = {
            row.name: str(row.get("patient_name") or row.name)
            for row in frappe.get_list(
                "Veterinary Patient",
                filters={"name": ["in", ids]},
                fields=["name", "patient_name"],
                page_length=len(ids),
            )
        }

    for row in rows:
        invoice = str(row.get("name") or row.get("invoice") or "")
        patient = patients.get(invoice, "")
        row["patient"] = patient
        row["patient_name"] = patient_names.get(patient, patient or "Owner-level / Unlinked")
        row["source_label"] = row.get("source_label") or "Other outstanding invoice for this owner"

    state["patient_outstanding_context"] = rows
    state["outstanding_context_scope"] = "owner"
    state["outstanding_context_label"] = "Other Outstanding Invoices for this Owner"
    state["outstanding_context_message"] = (
        "These invoices belong to the same Pet Owner/Customer but are outside the current billing cycle. "
        "The Patient column identifies the originating animal where VetEdge billing lineage is available."
    )
    return state


def _normalize_payload(payload: dict | None) -> dict:
    result = dict(payload or {})
    if isinstance(result.get("state"), dict):
        result["state"] = _enrich_owner_outstanding(result["state"])
    return result


def _prepare_active_billing_draft_dates(source_doctype: str, source_name: str) -> None:
    """Align the active draft before Billing Core re-dates it during an update.

    Billing Core intentionally uses the current date when an active draft invoice is
    updated. ERPNext validates due_date while preparing invoice defaults, so an older
    draft must have its posting/due date pair aligned before that preparation runs.
    Submitted/cancelled invoices are never changed here.
    """
    from vetedge.services.billing_core import is_billing_sessions_enabled, resolve_billing_session
    from vetedge.services.billing_modal import assert_can_act_on_source, get_billing_source_config
    from vetedge.services.platform_access import require_vetedge_platform_access

    config = get_billing_source_config(source_doctype)
    source_doc = frappe.get_doc(source_doctype, source_name)
    assert_can_act_on_source(source_doc, config)
    require_vetedge_platform_access(
        action="create_or_update_modal_invoice",
        reference_doctype=source_doctype,
        reference_name=source_name,
    )

    if not is_billing_sessions_enabled():
        return
    session = resolve_billing_session(source_doctype, source_name)
    if not session:
        return

    invoice_name = session.get("current_draft_invoice")
    if not invoice_name:
        latest_invoice = session.get("latest_invoice")
        if latest_invoice and frappe.db.exists("Sales Invoice", latest_invoice):
            if cint(frappe.db.get_value("Sales Invoice", latest_invoice, "docstatus")) == 0:
                invoice_name = latest_invoice
    if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
        return

    invoice = frappe.get_doc("Sales Invoice", invoice_name)
    if cint(invoice.get("docstatus")) != 0:
        return

    target_posting_date = nowdate()
    due_date = invoice.get("due_date") or target_posting_date
    needs_alignment = (
        not invoice.get("posting_date")
        or getdate(invoice.get("posting_date")) != getdate(target_posting_date)
        or getdate(due_date) < getdate(target_posting_date)
    )
    if not needs_alignment:
        return

    invoice.posting_date = target_posting_date
    if getdate(due_date) < getdate(target_posting_date):
        due_date = target_posting_date
    invoice.due_date = due_date
    invoice.save()


@frappe.whitelist()
def get_billing_modal_state(source_doctype: str, source_name: str) -> dict:
    require_internal_user()
    from vetedge.services.billing_state_security import get_billing_modal_state as original

    return _enrich_owner_outstanding(original(source_doctype=source_doctype, source_name=source_name))


@frappe.whitelist()
def create_or_update_modal_invoice(source_doctype: str, source_name: str) -> dict:
    require_internal_user()
    from vetedge.services.billing_state_security import create_or_update_modal_invoice as original

    _prepare_active_billing_draft_dates(source_doctype, source_name)
    return _normalize_payload(original(source_doctype=source_doctype, source_name=source_name))


@frappe.whitelist()
def submit_modal_invoice(source_doctype: str, source_name: str, invoice: str | None = None) -> dict:
    require_internal_user()
    from vetedge.services.billing_state_security import submit_modal_invoice as original

    return _normalize_payload(original(source_doctype=source_doctype, source_name=source_name, invoice=invoice))


@frappe.whitelist()
def record_modal_invoice_payment(
    source_doctype: str,
    source_name: str,
    invoice: str | None = None,
    amount: float | None = None,
    mode_of_payment: str | None = None,
    paid_to: str | None = None,
    posting_date: str | None = None,
    reference_no: str | None = None,
    reference_date: str | None = None,
    remarks: str | None = None,
) -> dict:
    require_internal_user()
    from vetedge.services.billing_state_security import record_modal_invoice_payment as original

    return _normalize_payload(
        original(
            source_doctype=source_doctype,
            source_name=source_name,
            invoice=invoice,
            amount=amount,
            mode_of_payment=mode_of_payment,
            paid_to=paid_to,
            posting_date=posting_date,
            reference_no=reference_no,
            reference_date=reference_date,
            remarks=remarks,
        )
    )
