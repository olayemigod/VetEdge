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
	"Veterinary Patient": BillingSourceConfig(
		source_doctype="Veterinary Patient",
		invoice_link_field="registration_invoice",
		patient_field="name",
		owner_field="primary_owner",
		branch_field="default_branch",
		create_invoice_method="vetedge.services.registration_billing.create_manual_registration_invoice",
		create_invoice_arg="patient",
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


def get_available_actions(
	config: BillingSourceConfig,
	invoice_summary: dict | None,
	session_summary: dict | None = None,
) -> dict:
	can_create_invoice = bool(config.create_invoice_method)
	if invoice_summary and cint(invoice_summary.get("docstatus")) == 1:
		can_create_invoice = False

	actions = {
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
	actions.update(get_modal_invoice_action_state(session_summary, invoice_summary, can_create_invoice))
	if session_summary:
		actions["can_create_invoice"] = actions["can_create_or_update_invoice"]
		actions["can_open_full_invoice"] = bool(actions.get("open_invoice_name"))
	return actions


def get_modal_invoice_action_state(
	session_summary: dict | None,
	invoice_summary: dict | None = None,
	legacy_can_create_invoice: bool = False,
) -> dict:
	state = {
		"current_draft_invoice": None,
		"latest_invoice": None,
		"latest_invoice_docstatus": None,
		"has_pending_charges": False,
		"pending_charge_count": 0,
		"can_create_or_update_invoice": False,
		"invoice_action_label": "No pending uninvoiced charges.",
		"open_invoice_label": None,
		"open_invoice_name": None,
	}

	if not session_summary:
		return get_legacy_modal_invoice_action_state(state, invoice_summary, legacy_can_create_invoice)

	invoices = session_summary.get("invoices") or []
	current_draft_invoice = session_summary.get("current_draft_invoice")
	latest_invoice = session_summary.get("latest_invoice")
	current_invoice_summary = find_session_invoice_summary(invoices, current_draft_invoice)
	latest_invoice_summary = find_session_invoice_summary(invoices, latest_invoice) or (invoices[-1] if invoices else None)
	current_docstatus = cint(current_invoice_summary.get("docstatus")) if current_invoice_summary else None
	latest_docstatus = cint(latest_invoice_summary.get("docstatus")) if latest_invoice_summary else None
	pending_charge_count = get_pending_session_charge_count(session_summary)

	state.update(
		{
			"current_draft_invoice": current_draft_invoice if current_docstatus == 0 else None,
			"latest_invoice": latest_invoice_summary.get("name") if latest_invoice_summary else latest_invoice,
			"latest_invoice_docstatus": latest_docstatus,
			"has_pending_charges": pending_charge_count > 0,
			"pending_charge_count": pending_charge_count,
		}
	)

	if current_invoice_summary and current_docstatus == 0:
		state["can_create_or_update_invoice"] = True
		state["invoice_action_label"] = "Update Draft Invoice"
	elif pending_charge_count > 0:
		state["can_create_or_update_invoice"] = True
		if not latest_invoice_summary:
			state["invoice_action_label"] = "Create Invoice"
		elif latest_docstatus == 1:
			state["invoice_action_label"] = "Create Next Invoice"
		elif latest_docstatus == 2:
			state["invoice_action_label"] = "Create New Invoice"
		else:
			state["invoice_action_label"] = "Create Invoice"

	open_invoice = current_invoice_summary if current_docstatus == 0 else latest_invoice_summary
	if open_invoice:
		docstatus = cint(open_invoice.get("docstatus"))
		state["open_invoice_name"] = open_invoice.get("name")
		if docstatus == 0:
			state["open_invoice_label"] = "Open Draft Invoice"
		elif docstatus == 1:
			state["open_invoice_label"] = "Open Submitted Invoice"
		else:
			state["open_invoice_label"] = "Open Latest Invoice"

	return state


def get_legacy_modal_invoice_action_state(state: dict, invoice_summary: dict | None, can_create_invoice: bool) -> dict:
	if invoice_summary:
		docstatus = cint(invoice_summary.get("docstatus"))
		state.update(
			{
				"latest_invoice": invoice_summary.get("name"),
				"latest_invoice_docstatus": docstatus,
				"open_invoice_name": invoice_summary.get("name"),
			}
		)
		if docstatus == 0:
			state["current_draft_invoice"] = invoice_summary.get("name")
			state["invoice_action_label"] = "Update Draft Invoice" if can_create_invoice else state["invoice_action_label"]
			state["open_invoice_label"] = "Open Draft Invoice"
		elif docstatus == 1:
			state["open_invoice_label"] = "Open Submitted Invoice"
		else:
			state["open_invoice_label"] = "Open Latest Invoice"
	else:
		state["invoice_action_label"] = "Create Invoice" if can_create_invoice else state["invoice_action_label"]
	state["can_create_or_update_invoice"] = bool(can_create_invoice)
	return state


def find_session_invoice_summary(invoices: list[dict], invoice_name: str | None) -> dict | None:
	if not invoice_name:
		return None
	for invoice in invoices:
		if invoice.get("name") == invoice_name:
			return invoice
	return None


def get_pending_session_charge_count(session_summary: dict | None) -> int:
	if not session_summary:
		return 0
	count = 0
	for charge in session_summary.get("charges") or []:
		if not charge.get("invoice") or charge.get("billing_status") == "Pending":
			count += 1
	return count


def is_billing_sessions_enabled() -> bool:
	try:
		from vetedge.services.billing_core import is_billing_sessions_enabled as core_is_billing_sessions_enabled

		return core_is_billing_sessions_enabled()
	except Exception:
		return False


def get_billing_session_summary_for_source(source_doctype: str, source_name: str) -> dict | None:
	try:
		from vetedge.services.billing_core import get_billing_session_summary, resolve_billing_session
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
		"Pet Grooming Session",
		"Pet Boarding Booking",
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


def get_billing_modal_totals(session_summary: dict | None, invoice_summary: dict | None) -> dict:
	current_total = flt(invoice_summary.get("grand_total")) if invoice_summary else 0
	current_paid = flt(invoice_summary.get("paid_amount")) if invoice_summary else 0
	current_outstanding = flt(invoice_summary.get("outstanding_amount")) if invoice_summary else 0
	current_name = invoice_summary.get("name") if invoice_summary else None
	current_status = invoice_summary.get("payment_status") or invoice_summary.get("status") if invoice_summary else None
	currency = invoice_summary.get("currency") if invoice_summary else None

	if not session_summary:
		return {
			"total_amount": current_total,
			"paid_amount": current_paid,
			"outstanding_amount": current_outstanding,
			"payment_status": current_status,
			"billing_session_total": 0,
			"billing_session_paid": 0,
			"billing_session_outstanding": 0,
			"billing_session_status": None,
			"linked_invoice_count": 0,
			"linked_invoices": [],
			"current_invoice_total": current_total,
			"current_invoice_paid": current_paid,
			"current_invoice_outstanding": current_outstanding,
			"current_invoice_name": current_name,
			"current_invoice_status": current_status,
			"currency": currency,
		}

	ledger = session_summary.get("invoice_ledger") or {}
	invoices = session_summary.get("invoices") or ledger.get("invoices") or []
	active_invoices = [row for row in invoices if not cint(row.get("docstatus")) == 2 and not row.get("is_cancelled")]
	linked_invoices = [row.get("name") or row.get("invoice") for row in active_invoices if row.get("name") or row.get("invoice")]
	currency = ledger.get("currency") or session_summary.get("currency") or currency
	session_total = flt(session_summary.get("total_invoiced") or ledger.get("total_invoiced"))
	session_paid = flt(session_summary.get("total_paid") or ledger.get("total_paid"))
	session_outstanding = flt(session_summary.get("outstanding_amount") or ledger.get("outstanding_amount"))
	return {
		"total_amount": session_total,
		"paid_amount": session_paid,
		"outstanding_amount": session_outstanding,
		"payment_status": session_summary.get("payment_status") or ledger.get("payment_status"),
		"billing_session_total": session_total,
		"billing_session_paid": session_paid,
		"billing_session_outstanding": session_outstanding,
		"billing_session_status": session_summary.get("payment_status") or ledger.get("payment_status"),
		"linked_invoice_count": len(linked_invoices),
		"linked_invoices": linked_invoices,
		"current_invoice_total": current_total,
		"current_invoice_paid": current_paid,
		"current_invoice_outstanding": current_outstanding,
		"current_invoice_name": current_name,
		"current_invoice_status": current_status,
		"currency": currency,
	}


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
	actions = get_available_actions(config, invoice_summary, session_summary)
	totals = get_billing_modal_totals(session_summary, invoice_summary)
	state = {
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
		"actions": actions,
		"payment_modes": get_payment_modes(),
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
			from vetedge.services.billing_core import sync_source_to_billing_session

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
