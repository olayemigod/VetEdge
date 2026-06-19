from __future__ import annotations

from dataclasses import dataclass

import frappe
from frappe.utils import cint, flt, getdate, nowdate

from vetedge.services.billing import get_invoice_access_summary, get_invoice_payment_status
from vetedge.services.permissions import can_access_branch_data
from vetedge.services.portal_access import require_internal_user


@dataclass(frozen=True)
class BillingSourceConfig:
	source_doctype: str
	invoice_link_field: str
	patient_field: str
	owner_field: str
	branch_field: str
	create_invoice_method: str | None = None
	create_invoice_arg: str | None = None
	payment_method: str | None = None
	payment_arg: str | None = None


BILLING_SOURCE_CONFIGS: dict[str, BillingSourceConfig] = {
	"Veterinary Consultation": BillingSourceConfig(
		source_doctype="Veterinary Consultation",
		invoice_link_field="linked_invoice",
		patient_field="patient",
		owner_field="primary_owner",
		branch_field="service_branch",
		create_invoice_method="vetedge.services.billing.create_consultation_invoice",
		create_invoice_arg="consultation",
		payment_method="vetedge.services.billing.create_payment_entry_from_consultation",
		payment_arg="consultation",
	),
	"Veterinary Vaccination Record": BillingSourceConfig(
		source_doctype="Veterinary Vaccination Record",
		invoice_link_field="linked_invoice",
		patient_field="patient",
		owner_field="primary_owner",
		branch_field="service_branch",
		create_invoice_method="vetedge.services.vaccination.create_or_update_vaccination_invoice",
		create_invoice_arg="record",
	),
	"Pet Grooming Session": BillingSourceConfig(
		source_doctype="Pet Grooming Session",
		invoice_link_field="linked_invoice",
		patient_field="patient",
		owner_field="primary_owner",
		branch_field="service_branch",
		create_invoice_method="vetedge.services.grooming.create_or_update_grooming_invoice",
		create_invoice_arg="session",
	),
	"Pet Boarding Booking": BillingSourceConfig(
		source_doctype="Pet Boarding Booking",
		invoice_link_field="linked_invoice",
		patient_field="patient",
		owner_field="primary_owner",
		branch_field="service_branch",
		create_invoice_method="vetedge.services.boarding.create_boarding_invoice",
		create_invoice_arg="booking",
	),
	"Veterinary Lab Order": BillingSourceConfig(
		source_doctype="Veterinary Lab Order",
		invoice_link_field="linked_invoice",
		patient_field="patient",
		owner_field="primary_owner",
		branch_field="service_branch",
		create_invoice_method="vetedge.services.lab.create_lab_order_invoice",
		create_invoice_arg="lab_order",
	),
	"Veterinary Hospitalisation": BillingSourceConfig(
		source_doctype="Veterinary Hospitalisation",
		invoice_link_field="sales_invoice",
		patient_field="patient",
		owner_field="customer",
		branch_field="service_branch",
		create_invoice_method="vetedge.services.hospitalisation.sync_hospitalisation_charges_to_invoice",
		create_invoice_arg="hospitalisation_name",
	),
}


def get_billing_source_config(source_doctype: str) -> BillingSourceConfig:
	config = BILLING_SOURCE_CONFIGS.get(source_doctype)
	if not config:
		frappe.throw(f"Billing modal is not configured for {source_doctype}.", frappe.ValidationError)
	return config


def assert_can_read_source(doc) -> None:
	if not frappe.has_permission(doc.doctype, "read", doc=doc):
		frappe.throw("You do not have permission to access this billing source.", frappe.PermissionError)

	if doc.doctype == "Veterinary Consultation":
		from vetedge.services.permissions import can_access_consultation

		can_access_consultation(frappe.session.user, doc.name, raise_exception=True)


def assert_can_act_on_source(doc, config: BillingSourceConfig) -> None:
	assert_can_read_source(doc)
	can_access_branch_data(frappe.session.user, doc.get(config.branch_field), raise_exception=True)


def get_linked_invoice_name(doc, config: BillingSourceConfig) -> str | None:
	invoice_name = doc.get(config.invoice_link_field)
	if invoice_name and frappe.db.exists("Sales Invoice", invoice_name):
		return invoice_name
	return None


def get_invoice_summary(invoice_name: str | None) -> dict | None:
	if not invoice_name:
		return None

	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	summary = get_invoice_access_summary(invoice_name)
	summary.update(
		{
			"name": invoice.name,
			"docstatus": cint(invoice.docstatus),
			"status": invoice.get("status"),
			"customer": invoice.get("customer"),
			"posting_date": invoice.get("posting_date"),
			"due_date": invoice.get("due_date"),
			"grand_total": flt(invoice.get("grand_total")),
			"total_taxes_and_charges": flt(invoice.get("total_taxes_and_charges")),
			"discount_amount": flt(invoice.get("discount_amount")),
			"paid_amount": flt(invoice.get("paid_amount")),
			"outstanding_amount": flt(invoice.get("outstanding_amount")),
			"currency": invoice.get("currency"),
			"payment_status": get_invoice_payment_status(invoice),
			"items": get_invoice_items(invoice),
			"taxes": get_invoice_taxes(invoice),
			"is_submitted": cint(invoice.docstatus) == 1,
			"is_draft": cint(invoice.docstatus) == 0,
			"is_cancelled": cint(invoice.docstatus) == 2,
		}
	)
	return summary


def get_invoice_items(invoice) -> list[dict]:
	return [
		{
			"item_code": row.get("item_code"),
			"item_name": row.get("item_name"),
			"description": row.get("description"),
			"qty": flt(row.get("qty")),
			"rate": flt(row.get("rate")),
			"amount": flt(row.get("amount")),
		}
		for row in invoice.get("items") or []
	]


def get_invoice_taxes(invoice) -> list[dict]:
	return [
		{
			"account_head": row.get("account_head"),
			"description": row.get("description"),
			"rate": flt(row.get("rate")),
			"tax_amount": flt(row.get("tax_amount")),
			"total": flt(row.get("total")),
		}
		for row in invoice.get("taxes") or []
	]


def get_display_value(doctype: str, name: str | None, fieldname: str | None = None) -> str | None:
	if not name:
		return None
	if fieldname and frappe.get_meta(doctype).has_field(fieldname):
		return frappe.db.get_value(doctype, name, fieldname) or name
	return name


def build_source_summary(doc, config: BillingSourceConfig) -> dict:
	patient = doc.get(config.patient_field)
	owner = doc.get(config.owner_field)
	branch = doc.get(config.branch_field)
	return {
		"doctype": doc.doctype,
		"name": doc.name,
		"status": doc.get("status"),
		"patient": patient,
		"patient_name": get_display_value("Veterinary Patient", patient, "patient_name"),
		"owner": owner,
		"owner_name": get_display_value("Customer", owner, "customer_name"),
		"service_branch": branch,
	}


def get_consultation_payment_gate_state(doc, invoice_summary: dict | None) -> dict | None:
	if doc.doctype != "Veterinary Consultation":
		return None

	from vetedge.services.payment_gate import (
		DRAFT_INVOICE_MESSAGE,
		FULL_PAYMENT_REQUIRED,
		FULL_PAYMENT_REQUIRED_MESSAGE,
		MISSING_INVOICE_MESSAGE,
		NO_PAYMENT_GATE,
		NO_PAYMENT_GATE_WARNING,
		PARTIAL_PAYMENT_GATE,
		PARTIAL_PAYMENT_REQUIRED_MESSAGE,
		get_consultation_payment_gate,
		get_invoice_payment_state,
		is_billable_consultation,
	)

	gate = get_consultation_payment_gate()
	billable = is_billable_consultation(doc)
	if not billable:
		return {
			"gate": gate,
			"billable": False,
			"can_proceed": True,
			"message": "This consultation is not billable, so no invoice or payment is required.",
		}

	if not invoice_summary:
		return {"gate": gate, "billable": True, "can_proceed": False, "message": MISSING_INVOICE_MESSAGE}
	if cint(invoice_summary.get("docstatus")) != 1:
		return {"gate": gate, "billable": True, "can_proceed": False, "message": DRAFT_INVOICE_MESSAGE}

	state = get_invoice_payment_state(invoice_summary["name"])
	if gate == NO_PAYMENT_GATE:
		return {
			"gate": gate,
			"billable": True,
			"can_proceed": True,
			"message": NO_PAYMENT_GATE_WARNING if flt(state.get("outstanding_amount")) > 0 else "Invoice is submitted.",
		}
	if gate == PARTIAL_PAYMENT_GATE:
		return {
			"gate": gate,
			"billable": True,
			"can_proceed": bool(state.get("has_payment")),
			"message": "A valid payment has been recorded." if state.get("has_payment") else PARTIAL_PAYMENT_REQUIRED_MESSAGE,
		}
	return {
		"gate": FULL_PAYMENT_REQUIRED,
		"billable": True,
		"can_proceed": bool(state.get("is_fully_paid")),
		"message": "Invoice is fully paid." if state.get("is_fully_paid") else FULL_PAYMENT_REQUIRED_MESSAGE,
	}


def get_available_actions(config: BillingSourceConfig, invoice_summary: dict | None) -> dict:
	can_create_invoice = bool(config.create_invoice_method)
	if invoice_summary and cint(invoice_summary.get("docstatus")) == 1:
		can_create_invoice = False

	return {
		"can_create_invoice": can_create_invoice,
		"can_submit_invoice": bool(invoice_summary and invoice_summary.get("is_draft")),
		"can_record_payment": bool(
			invoice_summary
			and invoice_summary.get("is_submitted")
			and flt(invoice_summary.get("outstanding_amount")) > 0
		),
		"can_open_full_invoice": bool(invoice_summary),
		"is_paid": bool(invoice_summary and invoice_summary.get("is_submitted") and flt(invoice_summary.get("outstanding_amount")) <= 0),
	}



def get_billing_session_summary_for_source(source_doctype: str, source_name: str) -> dict | None:
	try:
		from vetedge.services.billing_core import (
			get_billing_session_summary,
			is_billing_sessions_enabled,
			resolve_billing_session,
		)
	except Exception:
		return None
	if not is_billing_sessions_enabled():
		return None
	session = resolve_billing_session(source_doctype, source_name)
	if not session:
		return None
	return get_billing_session_summary(session)


def source_supports_billing_session(source_doctype: str) -> bool:
	return source_doctype in {
		"Veterinary Consultation",
		"Veterinary Lab Order",
		"Veterinary Hospitalisation",
		"Veterinary Vaccination Record",
		"Veterinary Patient",
	}


def get_primary_session_invoice_summary(session_summary: dict | None, fallback: dict | None = None) -> dict | None:
	if not session_summary:
		return fallback
	for invoice in session_summary.get("invoices") or []:
		if invoice.get("name") == session_summary.get("current_draft_invoice"):
			return get_invoice_summary(invoice.get("name")) or invoice
	for invoice in reversed(session_summary.get("invoices") or []):
		return get_invoice_summary(invoice.get("name")) or invoice
	return fallback


def get_payment_modes() -> list[str]:
	if not frappe.db.exists("DocType", "Mode of Payment"):
		return []
	return frappe.get_all(
		"Mode of Payment",
		filters={"enabled": 1},
		pluck="name",
		order_by="name asc",
	)


@frappe.whitelist()
def get_billing_modal_state(source_doctype: str, source_name: str) -> dict:
	require_internal_user()
	config = get_billing_source_config(source_doctype)
	doc = frappe.get_doc(source_doctype, source_name)
	assert_can_read_source(doc)
	invoice_name = get_linked_invoice_name(doc, config)
	invoice_summary = get_invoice_summary(invoice_name)
	session_summary = get_billing_session_summary_for_source(source_doctype, source_name)
	invoice_summary = get_primary_session_invoice_summary(session_summary, invoice_summary)
	return {
		"config": {
			"source_doctype": config.source_doctype,
			"invoice_link_field": config.invoice_link_field,
			"supports_invoice_creation": bool(config.create_invoice_method),
			"supports_modal_payment": bool(config.payment_method),
		},
		"source": build_source_summary(doc, config),
		"invoice": invoice_summary,
		"billing_session": session_summary,
		"payment_gate": (session_summary or {}).get("payment_gate") or get_consultation_payment_gate_state(doc, invoice_summary),
		"actions": get_available_actions(config, invoice_summary),
		"payment_modes": get_payment_modes(),
	}


@frappe.whitelist()
def create_invoice_from_modal(source_doctype: str, source_name: str) -> dict:
	return create_or_update_modal_invoice(source_doctype, source_name)


@frappe.whitelist()
def create_or_update_modal_invoice(source_doctype: str, source_name: str) -> dict:
	require_internal_user()
	config = get_billing_source_config(source_doctype)
	if not config.create_invoice_method or not config.create_invoice_arg:
		frappe.throw(f"Invoice creation is not supported for {source_doctype}.", frappe.ValidationError)

	doc = frappe.get_doc(source_doctype, source_name)
	assert_can_act_on_source(doc, config)
	invoice_name = get_linked_invoice_name(doc, config)
	invoice_summary = get_invoice_summary(invoice_name)
	if source_supports_billing_session(source_doctype):
		try:
			from vetedge.services.billing_core import is_billing_sessions_enabled, sync_source_to_billing_session

			if is_billing_sessions_enabled():
				result = sync_source_to_billing_session(source_doctype, source_name)
				return {"created": True, "result": result, "state": get_billing_modal_state(source_doctype, source_name)}
		except Exception:
			raise

	if invoice_summary and cint(invoice_summary.get("docstatus")) == 1:
		return {
			"created": False,
			"message": "An invoice is already linked to this document.",
			"state": get_billing_modal_state(source_doctype, source_name),
		}

	method = frappe.get_attr(config.create_invoice_method)
	result = method(**{config.create_invoice_arg: source_name})
	return {"created": True, "result": result, "state": get_billing_modal_state(source_doctype, source_name)}


@frappe.whitelist()
def create_payment_from_modal(source_doctype: str, source_name: str, mode_of_payment: str | None = None) -> dict:
	return record_modal_invoice_payment(
		source_doctype=source_doctype,
		source_name=source_name,
		mode_of_payment=mode_of_payment,
	)


@frappe.whitelist()
def submit_modal_invoice(source_doctype: str, source_name: str, invoice: str | None = None) -> dict:
	require_internal_user()
	config = get_billing_source_config(source_doctype)
	doc = frappe.get_doc(source_doctype, source_name)
	assert_can_act_on_source(doc, config)
	invoice_name = resolve_modal_invoice_name(doc, config, invoice)
	invoice_doc = frappe.get_doc("Sales Invoice", invoice_name)
	assert_invoice_is_linked_to_source_or_session(invoice_doc.name, doc, config)
	can_access_branch_data(frappe.session.user, invoice_doc.get("branch") or doc.get(config.branch_field), raise_exception=True)
	if cint(invoice_doc.docstatus) == 1:
		frappe.throw("The linked Sales Invoice is already submitted.", frappe.ValidationError)
	if cint(invoice_doc.docstatus) == 2:
		frappe.throw("Cancelled Sales Invoices cannot be submitted.", frappe.ValidationError)
	if not frappe.has_permission("Sales Invoice", "submit", doc=invoice_doc):
		frappe.throw("You do not have permission to submit this Sales Invoice.", frappe.PermissionError)

	ensure_invoice_due_date_not_before_posting_date(invoice_doc)
	invoice_doc.submit()
	return {"invoice": invoice_doc.name, "state": get_billing_modal_state(source_doctype, source_name)}


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
	config = get_billing_source_config(source_doctype)
	doc = frappe.get_doc(source_doctype, source_name)
	assert_can_act_on_source(doc, config)
	invoice_name = resolve_modal_invoice_name(doc, config, invoice)
	invoice_doc = frappe.get_doc("Sales Invoice", invoice_name)
	assert_invoice_is_linked_to_source_or_session(invoice_doc.name, doc, config)
	can_access_branch_data(frappe.session.user, invoice_doc.get("branch") or doc.get(config.branch_field), raise_exception=True)
	if cint(invoice_doc.docstatus) != 1:
		frappe.throw("Submit the Sales Invoice before recording payment.", frappe.ValidationError)
	outstanding = flt(invoice_doc.get("outstanding_amount"))
	if outstanding <= 0:
		frappe.throw("The linked Sales Invoice has no outstanding amount.", frappe.ValidationError)

	amount = flt(amount or outstanding)
	if amount <= 0:
		frappe.throw("Payment amount must be greater than zero.", frappe.ValidationError)
	if amount - outstanding > 0.0001:
		frappe.throw("Payment amount cannot exceed the outstanding amount.", frappe.ValidationError)
	if reference_no and submitted_payment_exists(invoice_doc.name, reference_no):
		frappe.throw("A submitted Payment Entry with this reference number already exists for this invoice.", frappe.ValidationError)

	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	payment_entry = get_payment_entry("Sales Invoice", invoice_doc.name)
	payment_entry.posting_date = getdate(posting_date or nowdate())
	if mode_of_payment:
		payment_entry.mode_of_payment = mode_of_payment
	if paid_to:
		payment_entry.paid_to = paid_to
	if reference_no:
		payment_entry.reference_no = reference_no
	if reference_date:
		payment_entry.reference_date = getdate(reference_date)
	if remarks:
		payment_entry.remarks = remarks

	payment_entry.paid_amount = amount
	payment_entry.received_amount = amount
	for reference in payment_entry.get("references") or []:
		if reference.reference_doctype == "Sales Invoice" and reference.reference_name == invoice_doc.name:
			reference.allocated_amount = amount

	if not frappe.has_permission("Payment Entry", "create", doc=payment_entry):
		frappe.throw("You do not have permission to create Payment Entries.", frappe.PermissionError)
	payment_entry.insert()
	if not frappe.has_permission("Payment Entry", "submit", doc=payment_entry):
		frappe.throw("You do not have permission to submit Payment Entries.", frappe.PermissionError)
	payment_entry.submit()

	return {
		"payment_entry": payment_entry.name,
		"invoice": invoice_doc.name,
		"state": get_billing_modal_state(source_doctype, source_name),
	}


def resolve_modal_invoice_name(doc, config: BillingSourceConfig, invoice: str | None = None) -> str:
	invoice_name = invoice or get_linked_invoice_name(doc, config)
	if not invoice_name:
		session_summary = get_billing_session_summary_for_source(doc.doctype, doc.name)
		if session_summary:
			invoice_name = session_summary.get("current_draft_invoice") or session_summary.get("latest_invoice")
	if not invoice_name:
		frappe.throw("A Sales Invoice must be generated before this action can continue.", frappe.ValidationError)
	if not frappe.db.exists("Sales Invoice", invoice_name):
		frappe.throw("The linked Sales Invoice could not be found.", frappe.ValidationError)
	return invoice_name


def ensure_invoice_due_date_not_before_posting_date(invoice) -> None:
	posting_date = get_effective_invoice_submit_posting_date(invoice)
	due_date = invoice.get("due_date")
	if not due_date or getdate(due_date) < posting_date:
		invoice.due_date = posting_date


def get_effective_invoice_submit_posting_date(invoice):
	posting_date = getdate(invoice.get("posting_date") or nowdate())
	if cint(invoice.get("set_posting_time")):
		return posting_date
	return max(posting_date, getdate(nowdate()))


def assert_invoice_is_linked_to_source(invoice_name: str, doc, config: BillingSourceConfig) -> None:
	linked_invoice = get_linked_invoice_name(doc, config)
	if linked_invoice == invoice_name:
		return
	frappe.throw("The selected Sales Invoice is not linked to this billing source.", frappe.PermissionError)


def assert_invoice_is_linked_to_source_or_session(invoice_name: str, doc, config: BillingSourceConfig) -> None:
	linked_invoice = get_linked_invoice_name(doc, config)
	if linked_invoice == invoice_name:
		return
	session_summary = get_billing_session_summary_for_source(doc.doctype, doc.name)
	if session_summary and any(row.get("name") == invoice_name for row in session_summary.get("invoices") or []):
		return
	frappe.throw("The selected Sales Invoice is not linked to this billing source.", frappe.PermissionError)


def submitted_payment_exists(invoice_name: str, reference_no: str) -> bool:
	names = frappe.get_all(
		"Payment Entry",
		filters={"reference_no": reference_no, "docstatus": 1},
		pluck="name",
		limit=20,
	)
	if not names:
		return False
	return bool(
		frappe.get_all(
			"Payment Entry Reference",
			filters={
				"parent": ["in", names],
				"reference_doctype": "Sales Invoice",
				"reference_name": invoice_name,
			},
			limit=1,
		)
	)
