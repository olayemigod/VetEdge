from __future__ import annotations

import frappe
from frappe.utils import cint, flt

from vetedge.services.billing import PAID_STATUS, get_invoice_payment_status
from vetedge.services.permissions import can_access_branch_data

BOARDING_DOCTYPE = "Pet Boarding Booking"
AMOUNT_TOLERANCE = 0.01
QTY_TOLERANCE = 0.0001


def _boarding_service():
    from vetedge.services import boarding

    return boarding


def _billing_modal_service():
    from vetedge.services import billing_modal

    return billing_modal


def _get_source(source_name: str, *, write: bool = False):
    billing_modal = _billing_modal_service()
    config = billing_modal.get_billing_source_config(BOARDING_DOCTYPE)
    doc = frappe.get_doc(BOARDING_DOCTYPE, source_name)
    if write:
        billing_modal.assert_can_act_on_source(doc, config)
    else:
        billing_modal.assert_can_read_source(doc)
    return doc, config


def _explicit_invoice_names(booking_doc) -> list[str]:
    boarding = _boarding_service()
    names: list[str] = []

    def add(name: str | None) -> None:
        value = str(name or "").strip()
        if value and value not in names and frappe.db.exists("Sales Invoice", value):
            names.append(value)

    for name in boarding.get_boarding_invoice_names(booking_doc):
        add(name)

    try:
        from vetedge.services.billing_core import get_billing_group_invoice_history

        for row in get_billing_group_invoice_history(
            BOARDING_DOCTYPE,
            booking_doc.name,
            include_related=False,
        ):
            add(row.get("name") or row.get("invoice"))
    except Exception:
        # The Boarding-specific references/remarks remain authoritative fallback
        # on sites where Billing Sessions are unavailable or partially migrated.
        pass

    return names


def get_boarding_invoice_documents(booking_doc) -> list:
    invoices = []
    for name in _explicit_invoice_names(booking_doc):
        invoice = frappe.get_doc("Sales Invoice", name)
        if cint(invoice.docstatus) == 2:
            continue
        invoices.append(invoice)
    invoices.sort(key=lambda row: (str(row.get("creation") or ""), row.name))
    return invoices


def _invoice_totals(booking_doc, invoices: list, *, submitted_only: bool = False) -> tuple[float, float]:
    boarding = _boarding_service()
    billed_days = 0.0
    billed_amount = 0.0
    for invoice in invoices:
        if submitted_only and cint(invoice.docstatus) != 1:
            continue
        qty, amount = boarding.get_boarding_invoice_totals(invoice, booking_doc)
        billed_days += flt(qty)
        billed_amount += flt(amount)
    return billed_days, billed_amount


def get_boarding_reconciliation(booking_doc) -> dict:
    boarding = _boarding_service()
    charges = boarding.calculate_boarding_charges(booking_doc)
    booking_doc.daily_rate = charges["daily_rate"]
    booking_doc.billable_days = charges["billable_days"]
    booking_doc.total_boarding_charge = charges["total_boarding_charge"]

    invoices = get_boarding_invoice_documents(booking_doc)
    drafts = [invoice for invoice in invoices if cint(invoice.docstatus) == 0]
    submitted = [invoice for invoice in invoices if cint(invoice.docstatus) == 1]

    submitted_days, submitted_amount = _invoice_totals(booking_doc, submitted)
    active_days, active_amount = _invoice_totals(booking_doc, invoices)
    draft_days, draft_amount = _invoice_totals(booking_doc, drafts)

    current_days = flt(booking_doc.billable_days)
    current_amount = flt(booking_doc.total_boarding_charge)
    delta_days = current_days - submitted_days
    delta_amount = current_amount - submitted_amount
    unbilled_days = current_days - active_days
    unbilled_amount = current_amount - active_amount

    all_submitted_paid = bool(submitted) and all(get_invoice_payment_status(invoice) == PAID_STATUS for invoice in submitted)
    checkout_can_proceed = (
        abs(unbilled_amount) < AMOUNT_TOLERANCE
        and abs(unbilled_days) < QTY_TOLERANCE
        and not drafts
        and (current_amount <= 0 or all_submitted_paid)
        and delta_amount >= -AMOUNT_TOLERANCE
    )

    return {
        "booking": booking_doc.name,
        "daily_rate": flt(booking_doc.daily_rate),
        "current_days": current_days,
        "current_amount": current_amount,
        "submitted_days": submitted_days,
        "submitted_amount": submitted_amount,
        "draft_days": draft_days,
        "draft_amount": draft_amount,
        "active_billed_days": active_days,
        "active_billed_amount": active_amount,
        "delta_days": delta_days,
        "delta_amount": delta_amount,
        "unbilled_days": unbilled_days,
        "unbilled_amount": unbilled_amount,
        "has_negative_submitted_delta": delta_amount < -AMOUNT_TOLERANCE or delta_days < -QTY_TOLERANCE,
        "all_submitted_paid": all_submitted_paid,
        "checkout_can_proceed": checkout_can_proceed,
        "invoices": invoices,
        "drafts": drafts,
        "submitted": submitted,
    }


def _negative_delta_message(reconciliation: dict) -> str:
    return (
        "The current boarding stay is lower than charges already submitted. "
        "Checkout requires financial review and the appropriate ERPNext credit/refund treatment; "
        "submitted Sales Invoices will not be reduced automatically."
    )


def validate_boarding_checkout_release_safety(booking_doc) -> None:
    reconciliation = get_boarding_reconciliation(booking_doc)
    current_amount = flt(reconciliation["current_amount"])

    if reconciliation["has_negative_submitted_delta"]:
        frappe.throw(_negative_delta_message(reconciliation), frappe.ValidationError)

    if current_amount > 0 and not reconciliation["invoices"]:
        frappe.throw("Create the boarding invoice before checking out this booking.", frappe.ValidationError)

    if (
        abs(flt(reconciliation["unbilled_amount"])) >= AMOUNT_TOLERANCE
        or abs(flt(reconciliation["unbilled_days"])) >= QTY_TOLERANCE
    ):
        amount = max(0.0, flt(reconciliation["unbilled_amount"]))
        frappe.throw(
            f"Boarding charges changed after billing. Bill the remaining {frappe.format_value(amount, {'fieldtype': 'Currency'})} before checkout.",
            frappe.ValidationError,
        )

    if reconciliation["drafts"]:
        frappe.throw("Submit and pay all boarding invoices before checking out this booking.", frappe.ValidationError)

    unpaid = [invoice for invoice in reconciliation["submitted"] if get_invoice_payment_status(invoice) != PAID_STATUS]
    if unpaid:
        frappe.throw("All boarding invoices must be fully paid before this booking can be checked out.", frappe.ValidationError)


def create_or_update_boarding_delta_invoice(source_name: str) -> dict:
    booking_doc, _config = _get_source(source_name, write=True)
    boarding = _boarding_service()

    if booking_doc.status == "Cancelled":
        frappe.throw("Cancelled boarding bookings cannot be billed.", frappe.ValidationError)

    reconciliation = get_boarding_reconciliation(booking_doc)
    if reconciliation["has_negative_submitted_delta"]:
        frappe.throw(_negative_delta_message(reconciliation), frappe.ValidationError)

    drafts = reconciliation["drafts"]
    if len(drafts) > 1:
        frappe.throw(
            "Multiple draft boarding invoices exist for this booking. Resolve them before creating another boarding invoice.",
            frappe.ValidationError,
        )

    delta_amount = flt(reconciliation["delta_amount"])
    delta_days = flt(reconciliation["delta_days"])
    if delta_amount < AMOUNT_TOLERANCE:
        if drafts:
            frappe.throw(
                "Submitted boarding invoices already cover the current stay. Review or remove the remaining draft adjustment before continuing.",
                frappe.ValidationError,
            )
        current_invoice = booking_doc.linked_invoice or (reconciliation["invoices"][-1].name if reconciliation["invoices"] else None)
        return {
            "name": booking_doc.name,
            "invoice": current_invoice,
            "open_invoice_name": current_invoice,
            "created": False,
            "adjustment": False,
            "reconciliation": _public_reconciliation(reconciliation),
        }

    if not booking_doc.billing_item:
        frappe.throw("Billing Item is required before a boarding invoice can be created.", frappe.ValidationError)

    cost_center = boarding.get_billing_cost_center(booking_doc.service_branch, required=True)
    item_payload = boarding.build_boarding_adjustment_invoice_item(
        booking_doc,
        cost_center,
        delta_days,
        delta_amount,
    )

    if drafts:
        invoice = boarding.update_draft_boarding_invoice(
            drafts[0].name,
            booking_doc,
            item_payload,
            cost_center,
        )
        created = False
    else:
        invoice = boarding.create_boarding_sales_invoice(
            booking_doc,
            item_payload,
            cost_center,
            adjustment=bool(reconciliation["submitted"]),
        )
        created = True

    refreshed = get_boarding_invoice_documents(booking_doc)
    if invoice.name not in {row.name for row in refreshed}:
        refreshed.append(invoice)
    refreshed.sort(key=lambda row: (str(row.get("creation") or ""), row.name))

    booking_doc.linked_invoice = invoice.name
    boarding.sync_boarding_invoice_references(booking_doc, refreshed)
    booking_doc.save(ignore_permissions=True)

    if created:
        boarding.emit_boarding_event(
            booking_doc,
            "boarding_invoice_created",
            extra={"invoice": invoice.name, "amount": getattr(invoice, "grand_total", item_payload.get("amount"))},
        )

    updated_reconciliation = get_boarding_reconciliation(booking_doc)
    return {
        "name": booking_doc.name,
        "invoice": invoice.name,
        "open_invoice_name": invoice.name,
        "created": created,
        "adjustment": bool(reconciliation["submitted"]),
        "reconciliation": _public_reconciliation(updated_reconciliation),
    }


def _history_rows(reconciliation: dict) -> list[dict]:
    billing_modal = _billing_modal_service()
    rows = []
    for invoice in reconciliation["invoices"]:
        summary = billing_modal.get_invoice_summary(invoice.name) or {}
        summary.update(
            {
                "source_doctype": BOARDING_DOCTYPE,
                "source_name": reconciliation["booking"],
                "relation_type": "boarding_booking",
            }
        )
        rows.append(summary)
    return billing_modal.enrich_invoice_history_for_modal(rows)


def _public_reconciliation(reconciliation: dict) -> dict:
    return {
        key: value
        for key, value in reconciliation.items()
        if key not in {"invoices", "drafts", "submitted"}
    }


def get_boarding_billing_modal_state(source_name: str) -> dict:
    booking_doc, config = _get_source(source_name, write=False)
    billing_modal = _billing_modal_service()
    reconciliation = get_boarding_reconciliation(booking_doc)
    history = _history_rows(reconciliation)
    drafts = reconciliation["drafts"]
    current_invoice_doc = drafts[0] if drafts else None
    if not current_invoice_doc and booking_doc.linked_invoice:
        current_invoice_doc = next((row for row in reconciliation["invoices"] if row.name == booking_doc.linked_invoice), None)
    if not current_invoice_doc and reconciliation["invoices"]:
        current_invoice_doc = reconciliation["invoices"][-1]

    invoice_summary = billing_modal.get_invoice_summary(current_invoice_doc.name) if current_invoice_doc else None
    delta_amount = flt(reconciliation["delta_amount"])
    delta_days = flt(reconciliation["delta_days"])
    negative_delta = reconciliation["has_negative_submitted_delta"]
    expected_draft_amount = max(0.0, delta_amount)
    draft_matches = bool(
        drafts
        and abs(flt(reconciliation["draft_amount"]) - expected_draft_amount) < AMOUNT_TOLERANCE
    )

    can_create_or_update = bool(not negative_delta and delta_amount >= AMOUNT_TOLERANCE and not draft_matches)
    if negative_delta:
        invoice_action_label = "Financial Review Required"
    elif drafts and draft_matches:
        invoice_action_label = "Draft Invoice Ready"
    elif drafts:
        invoice_action_label = "Update Draft Invoice"
    elif delta_amount >= AMOUNT_TOLERANCE:
        invoice_action_label = "Create Next Invoice" if reconciliation["submitted"] else "Create Invoice"
    else:
        invoice_action_label = "No pending uninvoiced charges."

    current_name = current_invoice_doc.name if current_invoice_doc else None
    current_docstatus = cint(current_invoice_doc.docstatus) if current_invoice_doc else None
    can_submit = bool(current_invoice_doc and current_docstatus == 0 and frappe.has_permission("Sales Invoice", "submit", doc=current_invoice_doc))
    can_pay = bool(
        current_invoice_doc
        and current_docstatus == 1
        and flt(current_invoice_doc.get("outstanding_amount")) > 0
        and frappe.has_permission("Payment Entry", "create")
        and frappe.has_permission("Payment Entry", "submit")
    )

    actions = {
        "can_create_invoice": can_create_or_update,
        "can_submit_invoice": can_submit,
        "can_record_payment": can_pay,
        "can_open_full_invoice": bool(current_name),
        "is_paid": reconciliation["checkout_can_proceed"],
        "current_draft_invoice": current_name if current_docstatus == 0 else None,
        "latest_invoice": reconciliation["invoices"][-1].name if reconciliation["invoices"] else None,
        "latest_invoice_docstatus": cint(reconciliation["invoices"][-1].docstatus) if reconciliation["invoices"] else None,
        "has_pending_charges": delta_amount >= AMOUNT_TOLERANCE and not draft_matches,
        "pending_charge_count": 1 if delta_amount >= AMOUNT_TOLERANCE and not draft_matches else 0,
        "can_create_or_update_invoice": can_create_or_update,
        "invoice_action_label": invoice_action_label,
        "open_invoice_label": (
            "Open Draft Invoice" if current_docstatus == 0 else "Open Submitted Invoice" if current_docstatus == 1 else None
        ),
        "open_invoice_name": current_name,
    }

    totals = billing_modal.get_billing_modal_totals(None, invoice_summary, history)
    patient_outstanding_context = billing_modal.get_patient_outstanding_context_for_modal(booking_doc, history)
    payment_gate = {
        "gate": "Boarding Checkout",
        "billable": flt(reconciliation["current_amount"]) > 0,
        "can_proceed": reconciliation["checkout_can_proceed"],
        "message": (
            "Boarding billing is reconciled and fully paid."
            if reconciliation["checkout_can_proceed"]
            else _negative_delta_message(reconciliation)
            if negative_delta
            else "Reconcile, submit and pay the current boarding charges before checkout."
        ),
    }

    state = {
        "config": {
            "source_doctype": config.source_doctype,
            "invoice_link_field": config.invoice_link_field,
            "supports_invoice_creation": True,
            "supports_modal_payment": False,
        },
        "source": billing_modal.build_source_summary(booking_doc, config),
        "invoice": invoice_summary,
        "invoice_history": history,
        "billing_group_invoice_history": history,
        "patient_outstanding_context": patient_outstanding_context,
        "billing_session": None,
        "payment_gate": payment_gate,
        "actions": actions,
        "payment_modes": billing_modal.get_payment_modes(),
        "boarding_reconciliation": _public_reconciliation(reconciliation),
        **totals,
    }
    for fieldname in (
        "current_draft_invoice",
        "latest_invoice",
        "latest_invoice_docstatus",
        "has_pending_charges",
        "pending_charge_count",
        "can_create_or_update_invoice",
        "invoice_action_label",
        "open_invoice_label",
        "open_invoice_name",
    ):
        state[fieldname] = actions.get(fieldname)
    return state


def submit_boarding_modal_invoice(source_name: str, invoice: str | None = None) -> dict:
    booking_doc, config = _get_source(source_name, write=True)
    reconciliation = get_boarding_reconciliation(booking_doc)
    invoice_name = str(invoice or "").strip()
    if not invoice_name:
        if reconciliation["drafts"]:
            invoice_name = reconciliation["drafts"][0].name
        else:
            invoice_name = str(booking_doc.linked_invoice or "").strip()
    if not invoice_name or invoice_name not in {row.name for row in reconciliation["invoices"]}:
        frappe.throw("The selected Sales Invoice is not linked to this boarding booking.", frappe.PermissionError)

    invoice_doc = frappe.get_doc("Sales Invoice", invoice_name)
    can_access_branch_data(
        frappe.session.user,
        invoice_doc.get("branch") or booking_doc.get(config.branch_field),
        raise_exception=True,
    )
    if cint(invoice_doc.docstatus) == 1:
        frappe.throw("The linked Sales Invoice is already submitted.", frappe.ValidationError)
    if cint(invoice_doc.docstatus) == 2:
        frappe.throw("Cancelled Sales Invoices cannot be submitted.", frappe.ValidationError)
    if not frappe.has_permission("Sales Invoice", "submit", doc=invoice_doc):
        frappe.throw("You do not have permission to submit this Sales Invoice.", frappe.PermissionError)

    from vetedge.services.billing_core import prepare_vetedge_invoice_for_submit

    prepare_vetedge_invoice_for_submit(invoice_doc, verified_vetedge_link=True)
    invoice_doc.submit()
    return {"invoice": invoice_doc.name, "state": get_boarding_billing_modal_state(source_name)}


def record_boarding_modal_payment(
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
    booking_doc, _config = _get_source(source_name, write=True)
    reconciliation = get_boarding_reconciliation(booking_doc)
    invoice_name = str(invoice or booking_doc.linked_invoice or "").strip()
    if not invoice_name or invoice_name not in {row.name for row in reconciliation["invoices"]}:
        frappe.throw("The selected Sales Invoice is not linked to this boarding booking.", frappe.PermissionError)

    billing_modal = _billing_modal_service()
    result = billing_modal.record_modal_invoice_payment(
        source_doctype=BOARDING_DOCTYPE,
        source_name=source_name,
        invoice=invoice_name,
        amount=amount,
        mode_of_payment=mode_of_payment,
        paid_to=paid_to,
        posting_date=posting_date,
        reference_no=reference_no,
        reference_date=reference_date,
        remarks=remarks,
    )
    result["state"] = get_boarding_billing_modal_state(source_name)
    return result
