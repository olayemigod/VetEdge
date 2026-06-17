from __future__ import annotations

import frappe
from frappe.utils import cint, flt


FULL_PAYMENT_REQUIRED = "Full Payment Required"
PARTIAL_PAYMENT_GATE = "Partial Payment Gate"
NO_PAYMENT_GATE = "No Payment Gate"
CONSULTATION_PAYMENT_GATE_OPTIONS = {
	FULL_PAYMENT_REQUIRED,
	PARTIAL_PAYMENT_GATE,
	NO_PAYMENT_GATE,
}
CONSULTATION_PROCEED_STATUSES = {
	"In Progress",
	"Pending Dispensary",
	"Ready for Treatment",
	"Completed",
}

MISSING_INVOICE_MESSAGE = "A Sales Invoice must be generated before this consultation can proceed."
DRAFT_INVOICE_MESSAGE = "The linked Sales Invoice must be submitted before this consultation can proceed."
PARTIAL_PAYMENT_REQUIRED_MESSAGE = "A partial payment is required before this consultation can proceed."
FULL_PAYMENT_REQUIRED_MESSAGE = "Full payment is required before this consultation can proceed."
NO_PAYMENT_GATE_WARNING = "This consultation is allowed without payment because No Payment Gate is enabled. The invoice remains outstanding."


def get_consultation_payment_gate() -> str:
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return FULL_PAYMENT_REQUIRED

	settings = frappe.get_single("Veterinary Settings")
	meta = frappe.get_meta("Veterinary Settings")
	if not meta.has_field("consultation_payment_gate"):
		return FULL_PAYMENT_REQUIRED

	gate = settings.get("consultation_payment_gate") or FULL_PAYMENT_REQUIRED
	if gate not in CONSULTATION_PAYMENT_GATE_OPTIONS:
		return FULL_PAYMENT_REQUIRED
	return gate


def ensure_billable_invoice_exists(doc) -> list[str]:
	if not is_billable_consultation(doc):
		return []

	invoice_names = get_consultation_invoice_names_for_gate(doc)
	if not invoice_names:
		frappe.throw(MISSING_INVOICE_MESSAGE, frappe.ValidationError)

	for invoice_name in invoice_names:
		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		if cint(invoice.docstatus) != 1:
			frappe.throw(DRAFT_INVOICE_MESSAGE, frappe.ValidationError)

	return invoice_names


def get_invoice_payment_state(invoice_name: str) -> dict:
	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	allocated_amount = get_submitted_payment_entry_allocated_amount(invoice_name)
	invoice_payment_rows_paid_amount = get_invoice_payment_rows_paid_amount(invoice)
	fallback_paid_amount = max(
		flt(invoice.get("paid_amount")),
		flt(invoice.get("grand_total")) - flt(invoice.get("outstanding_amount")),
		0,
	)
	paid_amount = max(allocated_amount, invoice_payment_rows_paid_amount, fallback_paid_amount)

	return {
		"invoice": invoice_name,
		"docstatus": cint(invoice.docstatus),
		"grand_total": flt(invoice.get("grand_total")),
		"outstanding_amount": flt(invoice.get("outstanding_amount")),
		"allocated_amount": allocated_amount,
		"invoice_payment_rows_paid_amount": invoice_payment_rows_paid_amount,
		"paid_amount": paid_amount,
		"has_payment": paid_amount > 0,
		"is_fully_paid": cint(invoice.docstatus) == 1 and flt(invoice.get("outstanding_amount")) <= 0,
	}


def has_valid_payment(invoice_name: str) -> bool:
	return bool(get_invoice_payment_state(invoice_name).get("has_payment"))


def assert_consultation_can_proceed(doc, target_status: str | None = None) -> None:
	target_status = target_status or doc.get("status")
	if target_status not in CONSULTATION_PROCEED_STATUSES:
		return

	invoice_names = ensure_billable_invoice_exists(doc)
	if not invoice_names:
		return

	gate = get_consultation_payment_gate()
	if gate == NO_PAYMENT_GATE:
		notify_no_payment_gate_warning(invoice_names)
		return

	for invoice_name in invoice_names:
		state = get_invoice_payment_state(invoice_name)
		if gate == PARTIAL_PAYMENT_GATE:
			if not state["has_payment"]:
				frappe.throw(PARTIAL_PAYMENT_REQUIRED_MESSAGE, frappe.ValidationError)
			continue

		if not state["is_fully_paid"]:
			frappe.throw(FULL_PAYMENT_REQUIRED_MESSAGE, frappe.ValidationError)


def is_billable_consultation(doc) -> bool:
	from vetedge.services.billing import consultation_requires_invoice_before_progress

	return bool(consultation_requires_invoice_before_progress(doc, "Ready for Treatment"))


def get_consultation_invoice_names_for_gate(doc) -> list[str]:
	from vetedge.services.billing import get_consultation_invoice_names

	return get_consultation_invoice_names(doc)


def get_submitted_payment_entry_allocated_amount(invoice_name: str) -> float:
	if not frappe.db.exists("DocType", "Payment Entry Reference"):
		return 0

	rows = frappe.get_all(
		"Payment Entry Reference",
		filters={
			"reference_doctype": "Sales Invoice",
			"reference_name": invoice_name,
		},
		fields=["parent", "allocated_amount"],
	)
	total = 0
	for row in rows:
		if row.get("parent") and cint(frappe.db.get_value("Payment Entry", row.get("parent"), "docstatus")) == 1:
			total += flt(row.get("allocated_amount"))
	return total


def get_invoice_payment_rows_paid_amount(invoice) -> float:
	if cint(invoice.docstatus) != 1:
		return 0

	payments = invoice.get("payments") or []
	return sum(flt(payment.get("amount")) for payment in payments)


def notify_no_payment_gate_warning(invoice_names: list[str]) -> None:
	try:
		frappe.msgprint(NO_PAYMENT_GATE_WARNING, indicator="orange", alert=True)
	except Exception:
		pass
