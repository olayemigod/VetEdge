from __future__ import annotations

import json
from collections import OrderedDict
from typing import Iterable

import frappe
from frappe.utils import cint, flt, getdate, nowdate

from vetedge.services.payment_gate import (
	FULL_PAYMENT_REQUIRED,
	NO_PAYMENT_GATE,
	PARTIAL_PAYMENT_GATE,
	get_invoice_payment_state,
)
from vetedge.services.registration_billing import get_billing_cost_center, get_default_company


BILLING_SESSION_DOCTYPE = "Veterinary Billing Session"
BILLING_SESSION_CHARGE_DOCTYPE = "Veterinary Billing Session Charge"
FULL_PAYMENT_GATE = "Full Payment Gate"
PAYMENT_GATE_ALIASES = {
	FULL_PAYMENT_REQUIRED: FULL_PAYMENT_GATE,
	FULL_PAYMENT_GATE: FULL_PAYMENT_GATE,
	PARTIAL_PAYMENT_GATE: PARTIAL_PAYMENT_GATE,
	NO_PAYMENT_GATE: NO_PAYMENT_GATE,
}
PENDING_STATUSES = {"Pending", "Draft Invoiced"}
FINAL_INVOICE_STATUSES = {"Submitted Invoiced", "Paid", "Cancelled", "Skipped"}
ACTIVE_SESSION_STATUSES = {"Draft", "Active", "Partially Paid"}
SUPPORTED_BILLING_SOURCE_DOCTYPES = {
	"Veterinary Consultation",
	"Veterinary Lab Order",
	"Veterinary Hospitalisation",
	"Veterinary Vaccination Record",
	"Veterinary Patient",
	"Pet Grooming Session",
	"Pet Boarding Booking",
}
SAFE_SOURCE_INVOICE_LINK_FIELDS = {
	"Veterinary Consultation": {"field": "linked_invoice", "status_field": "payment_status", "empty_status": "Not Billed"},
	"Veterinary Lab Order": {"field": "linked_invoice"},
	"Veterinary Vaccination Record": {"field": "linked_invoice"},
	"Veterinary Hospitalisation": {"field": "sales_invoice", "status_field": "invoice_status", "empty_status": "Not Invoiced"},
	"Veterinary Patient": {"field": "registration_invoice", "extra_values": {"registration_billed": 0}},
	"Pet Grooming Session": {"field": "linked_invoice"},
	"Pet Grooming Appointment": {"field": "linked_invoice"},
	"Pet Boarding Booking": {"field": "linked_invoice"},
	"Veterinary Guest Booking Request": {"field": "registration_invoice"},
}
SAFE_SOURCE_INVOICE_CHILD_LINK_FIELDS = {
	"Consultation Invoice Reference": {"field": "sales_invoice", "action": "delete"},
	"Consultation Billing Source": {"field": "sales_invoice", "action": "clear"},
	"Boarding Invoice Reference": {"field": "sales_invoice", "action": "delete"},
	"Veterinary Hospitalisation Charge Item": {"field": "sales_invoice", "action": "clear", "extra_values": {"sales_invoice_item": None}},
}


def is_billing_sessions_enabled() -> bool:
	if not frappe.db.exists("DocType", BILLING_SESSION_DOCTYPE):
		return False
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return True
	meta = frappe.get_meta("Veterinary Settings")
	if not meta.has_field("enable_billing_sessions"):
		return True
	return bool(cint(frappe.get_single("Veterinary Settings").get("enable_billing_sessions")))



def should_sync_related_billable_sources_to_session() -> bool:
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return True
	meta = frappe.get_meta("Veterinary Settings")
	if not meta.has_field("sync_related_billable_sources_to_session"):
		return True
	return bool(cint(frappe.get_single("Veterinary Settings").get("sync_related_billable_sources_to_session")))


def get_active_session_status_filter():
	return ["in", sorted(ACTIVE_SESSION_STATUSES)]


def get_open_session_status_filter():
	return ["not in", ["Closed", "Cancelled"]]


def is_billing_session_open_for_continuity(session) -> bool:
	return bool(session and session.get("status") not in {"Closed", "Cancelled"})


def find_registration_billing_session_for_consultation(identity: dict | None):
	identity = identity or {}
	patient = identity.get("patient")
	customer = identity.get("customer")
	if not patient or not customer:
		return None
	filters = {
		"animal": patient,
		"customer": customer,
		"status": get_open_session_status_filter(),
	}
	rows = frappe.get_all(
		BILLING_SESSION_DOCTYPE,
		filters=filters,
		fields=["name", "created_from_doctype", "source_context_doctype", "current_draft_invoice", "latest_invoice", "status"],
		order_by="modified desc",
	)
	fallback = None
	for row in rows:
		session = frappe.get_doc(BILLING_SESSION_DOCTYPE, row.name)
		if not is_billing_session_open_for_continuity(session):
			continue
		if session_is_registration_origin(session):
			return session
		if fallback is None and session_has_active_draft_or_pending_charges(session):
			fallback = session
	return fallback


def session_is_registration_origin(session) -> bool:
	if session.get("created_from_doctype") == "Veterinary Patient" or session.get("source_context_doctype") == "Veterinary Patient":
		return True
	return bool(
		frappe.get_all(
			BILLING_SESSION_CHARGE_DOCTYPE,
			filters={"parent": session.name, "source_doctype": "Veterinary Patient"},
			fields=["name"],
			limit=1,
		)
	)


def session_has_active_draft_or_pending_charges(session) -> bool:
	invoice_name = session.get("current_draft_invoice") or session.get("latest_invoice")
	if invoice_name and frappe.db.exists("Sales Invoice", invoice_name):
		if cint(frappe.db.get_value("Sales Invoice", invoice_name, "docstatus")) == 0:
			return True
	return any(row.get("billing_status") in PENDING_STATUSES for row in session.get("charges") or [])


def normalize_payment_gate_mode(mode: str | None = None) -> str:
	if mode in PAYMENT_GATE_ALIASES:
		return PAYMENT_GATE_ALIASES[mode]
	if frappe.db.exists("DocType", "Veterinary Settings"):
		meta = frappe.get_meta("Veterinary Settings")
		settings = frappe.get_single("Veterinary Settings")
		if meta.has_field("default_payment_gate_mode") and settings.get("default_payment_gate_mode"):
			return PAYMENT_GATE_ALIASES.get(settings.get("default_payment_gate_mode"), FULL_PAYMENT_GATE)
	return FULL_PAYMENT_GATE


def resolve_billing_session(source_doctype: str, source_name: str):
	if not is_billing_sessions_enabled():
		return None
	if source_uses_explicit_billing_session(source_doctype):
		session_name = frappe.db.get_value(source_doctype, source_name, "billing_session")
		if session_name and frappe.db.exists(BILLING_SESSION_DOCTYPE, session_name):
			session = frappe.get_doc(BILLING_SESSION_DOCTYPE, session_name)
			if is_billing_session_open_for_continuity(session):
				return session
	rows = frappe.get_all(
		BILLING_SESSION_CHARGE_DOCTYPE,
		filters={"source_doctype": source_doctype, "source_name": source_name},
		fields=["parent"],
		order_by="modified desc",
		limit=1,
	)
	if rows:
		return frappe.get_doc(BILLING_SESSION_DOCTYPE, rows[0].parent)

	identity = get_source_billing_identity(source_doctype, source_name)
	if source_doctype == "Veterinary Consultation":
		registration_session = find_registration_billing_session_for_consultation(identity)
		if registration_session:
			return registration_session

	context = get_source_context(source_doctype, source_name)
	if context != (source_doctype, source_name):
		rows = frappe.get_all(
			BILLING_SESSION_DOCTYPE,
			filters={"source_context_doctype": context[0], "source_context_name": context[1], "status": get_active_session_status_filter()},
			fields=["name"],
			order_by="modified desc",
			limit=1,
		)
		if rows:
			return frappe.get_doc(BILLING_SESSION_DOCTYPE, rows[0].name)

	consultation = identity.get("consultation") or find_active_consultation_for_identity(identity)
	if consultation and source_doctype != "Veterinary Consultation":
		consultation_session = resolve_billing_session("Veterinary Consultation", consultation)
		if consultation_session and consultation_session.get("status") in ACTIVE_SESSION_STATUSES:
			return consultation_session

	if identity.get("patient") and identity.get("customer"):
		rows = frappe.get_all(
			BILLING_SESSION_DOCTYPE,
			filters={
				"animal": identity.get("patient"),
				"customer": identity.get("customer"),
				"status": get_active_session_status_filter(),
			},
			fields=["name"],
			order_by="modified desc",
			limit=1,
		)
		if rows:
			return frappe.get_doc(BILLING_SESSION_DOCTYPE, rows[0].name)
	return None


def get_or_create_billing_session(
	source_doctype: str,
	source_name: str,
	customer: str | None = None,
	animal: str | None = None,
	company: str | None = None,
	branch: str | None = None,
	payment_gate_mode: str | None = None,
):
	if not is_billing_sessions_enabled():
		frappe.throw("Billing Sessions are not enabled.", frappe.ValidationError)

	existing = resolve_billing_session(source_doctype, source_name)
	if existing:
		return update_session_context(existing, customer, animal, company, branch, payment_gate_mode)

	source_doc = frappe.get_doc(source_doctype, source_name)
	identity = get_source_billing_identity(source_doctype, source_name, source_doc)
	customer = customer or identity.get("customer") or source_doc.get("primary_owner") or source_doc.get("customer")
	animal = animal or identity.get("patient") or source_doc.get("patient") or source_doc.get("animal")
	branch = branch or identity.get("branch") or source_doc.get("service_branch") or source_doc.get("branch")
	company = company or identity.get("company") or source_doc.get("company") or get_default_company()
	if not customer:
		frappe.throw("Customer is required before creating a Billing Session.", frappe.ValidationError)

	context_doctype, context_name = get_source_context(source_doctype, source_name)
	session = frappe.get_doc(
		{
			"doctype": BILLING_SESSION_DOCTYPE,
			"naming_series": "VBS-.YYYY.-.#####",
			"customer": customer,
			"animal": animal,
			"company": company,
			"branch": branch,
			"status": "Active",
			"payment_gate_mode": normalize_payment_gate_mode(payment_gate_mode or get_source_payment_gate_mode(source_doctype)),
			"source_context_doctype": context_doctype,
			"source_context_name": context_name,
			"created_from_doctype": source_doctype,
			"created_from_name": source_name,
		}
	)
	session.insert()
	return session


def update_session_context(session, customer=None, animal=None, company=None, branch=None, payment_gate_mode=None):
	changed = False
	for fieldname, value in {
		"customer": customer,
		"animal": animal,
		"company": company,
		"branch": branch,
		"payment_gate_mode": normalize_payment_gate_mode(payment_gate_mode) if payment_gate_mode else None,
	}.items():
		if value and session.get(fieldname) != value:
			session.set(fieldname, value)
			changed = True
	if changed:
		session.save()
	return session


def add_or_update_session_charge(session, charge_payload: dict):
	return upsert_source_charge_payload(session, charge_payload)


def upsert_source_charge_payload(session, payload: dict):
	charge = frappe._dict(payload or {})
	charge_key = charge.get("charge_key") or build_charge_key(charge)
	if not charge_key:
		frappe.throw("Billing Session charge_key is required.", frappe.ValidationError)

	existing = get_existing_charge_by_key(session, charge_key)
	values = normalize_charge_payload(charge, charge_key, session)
	if existing:
		if is_charge_already_submitted(existing) or existing.get("billing_status") in {"Cancelled", "Skipped"}:
			return existing
		for fieldname, value in values.items():
			setattr(existing, fieldname, value)
		existing.billing_status = existing.get("billing_status") or "Pending"
		return existing

	row = session.append("charges", values)
	row.billing_status = row.get("billing_status") or "Pending"
	return row


def sync_session_charges_to_invoice(session, confirm: bool = False, confirmation_type: str | None = None):
	confirm = bool(cint(confirm))
	session = ensure_session_doc(session)
	reconcile_session_charge_statuses(session)
	submitted_action = get_retired_submitted_invoice_action(session, confirm=confirm, confirmation_type=confirmation_type)
	if submitted_action:
		return submitted_action
	active_draft = _get_active_draft_invoice(session)
	removed_count = remove_retired_charge_items_from_draft_invoice(session, active_draft)
	pending = _get_pending_charges_for_invoice(session, active_draft)
	if not pending:
		if active_draft and removed_count:
			if not (active_draft.get("items") or []):
				if not (confirm and confirmation_type == "remove_empty_draft_invoice"):
					return {
						"session": session.name,
						"invoice": active_draft.name,
						"created": False,
						"added_count": 0,
						"updated_count": 0,
						"removed_count": removed_count,
						"requires_confirmation": True,
						"confirmation_type": "remove_empty_draft_invoice",
						"billing_session": session.name,
						"message": "Removing these charges will leave the draft invoice empty. Confirm to remove the draft invoice.",
						"reload_required": True,
					}
				return remove_empty_draft_invoice_for_session(session, active_draft, removed_count)
			_prepare_sales_invoice_totals(active_draft)
			normalize_billing_session_invoice_dates(active_draft)
			run_with_billing_core_sync_flag(active_draft.save)
		refresh_billing_session_totals(session)
		session.save()
		return {"session": session.name, "invoice": active_draft.name if active_draft else None, "created": False, "added_count": 0, "updated_count": 0, "removed_count": removed_count}

	invoice, created = create_or_update_draft_invoice_for_session(session, pending)
	if not invoice:
		refresh_billing_session_totals(session)
		session.save()
		return {"session": session.name, "invoice": None, "created": False, "added_count": 0, "updated_count": 0}
	item_index = get_invoice_item_charge_index(invoice)
	added = updated = 0
	for charge in pending:
		key = charge.get("charge_key")
		if key in item_index:
			update_invoice_item_from_charge(item_index[key], charge)
			if created:
				added += 1
			else:
				updated += 1
		else:
			item_index[key] = append_invoice_item_from_charge(invoice, charge)
			added += 1
		charge.invoice = invoice.name
		charge.invoice_item_name = item_index[key].get("name")
		charge.billing_status = "Draft Invoiced"

	_prepare_sales_invoice_totals(invoice)
	normalize_billing_session_invoice_dates(invoice)
	run_with_billing_core_sync_flag(invoice.save)
	session = update_session_after_invoice_sync(session.name, invoice.name, [row.get("charge_key") for row in pending])
	return {"session": session.name, "invoice": invoice.name, "created": created, "added_count": added, "updated_count": updated, "removed_count": removed_count}


def create_or_update_draft_invoice_for_session(session, pending_charges=None):
	session = ensure_session_doc(session)
	reconcile_session_charge_statuses(session)
	invoice = _get_active_draft_invoice(session)
	pending_charges = list(pending_charges) if pending_charges is not None else _get_pending_charges_for_invoice(session, invoice)
	if invoice:
		apply_invoice_session_defaults(invoice, session)
		return invoice, False

	if not pending_charges:
		return None, False

	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": session.customer,
			"company": session.company or get_default_company(),
			"posting_date": nowdate(),
			"due_date": nowdate(),
			"update_stock": 0,
			"items": [],
			"remarks": f"VetEdge billing session {session.name}",
		}
	)
	apply_invoice_session_defaults(invoice, session)
	for charge in pending_charges:
		append_invoice_item_from_charge(invoice, charge)
	_prepare_sales_invoice_totals(invoice)
	normalize_billing_session_invoice_dates(invoice)
	run_with_billing_core_sync_flag(invoice.insert)
	session.current_draft_invoice = invoice.name
	session.latest_invoice = invoice.name
	return invoice, True


def _get_active_draft_invoice(session):
	session = ensure_session_doc(session)
	invoice_name = session.get("current_draft_invoice")
	if invoice_name and frappe.db.exists("Sales Invoice", invoice_name):
		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		if cint(invoice.docstatus) == 0:
			return invoice
		session.current_draft_invoice = None
	elif invoice_name:
		session.current_draft_invoice = None

	latest_invoice = session.get("latest_invoice")
	if latest_invoice and latest_invoice != invoice_name and frappe.db.exists("Sales Invoice", latest_invoice):
		invoice = frappe.get_doc("Sales Invoice", latest_invoice)
		if cint(invoice.docstatus) == 0:
			session.current_draft_invoice = invoice.name
			return invoice
	return None


def _get_pending_charges_for_invoice(session, draft_invoice=None):
	session = ensure_session_doc(session)
	draft_invoice_name = draft_invoice.name if draft_invoice else None
	pending = []
	for row in session.get("charges") or []:
		if row.get("billing_status") in {"Cancelled", "Skipped"}:
			continue
		invoice_name = row.get("invoice")
		if not invoice_name:
			if row.get("billing_status") not in FINAL_INVOICE_STATUSES:
				pending.append(row)
			continue
		if not frappe.db.exists("Sales Invoice", invoice_name):
			row.invoice = None
			row.invoice_item_name = None
			if row.get("billing_status") != "Skipped":
				row.billing_status = "Pending"
				pending.append(row)
			continue
		docstatus = cint(frappe.db.get_value("Sales Invoice", invoice_name, "docstatus"))
		if docstatus == 0 and invoice_name == draft_invoice_name:
			pending.append(row)
		elif docstatus == 0 and not draft_invoice_name:
			pending.append(row)
		elif docstatus == 2:
			row.billing_status = "Cancelled"
	return pending


@frappe.whitelist()
def diagnose_billing_session_unbilled_items(source_doctype: str, source_name: str) -> dict:
	session = sync_source_charge_payloads_to_billing_session(source_doctype, source_name)
	source_payloads = get_source_charge_payloads(source_doctype, source_name, session)
	existing = {row.get("charge_key"): row for row in session.get("charges") or []}
	submitted = []
	draft = []
	pending = []
	rows = []
	for payload in source_payloads:
		charge_key = payload.get("charge_key") or build_charge_key(payload)
		charge = existing.get(charge_key)
		invoice_name = charge.get("invoice") if charge else None
		docstatus = None
		if invoice_name and frappe.db.exists("Sales Invoice", invoice_name):
			docstatus = cint(frappe.db.get_value("Sales Invoice", invoice_name, "docstatus"))
		if docstatus == 1:
			submitted.append(charge_key)
		elif docstatus == 0:
			draft.append(charge_key)
		elif not charge or not invoice_name or charge.get("billing_status") == "Pending":
			pending.append(charge_key)
		rows.append(
			{
				"charge_key": charge_key,
				"source_detail_name": payload.get("source_detail_name"),
				"item_code": payload.get("item_code"),
				"existing": bool(charge),
				"invoice": invoice_name,
				"invoice_docstatus": docstatus,
				"billing_status": charge.get("billing_status") if charge else "Unbilled",
				"reason": get_unbilled_diagnostic_reason(charge, docstatus),
			}
		)
	ledger = get_billing_session_invoice_ledger(session)
	gate = get_payment_gate_status(session)
	return {
		"session": session.name,
		"source_payload_charge_keys": [payload.get("charge_key") or build_charge_key(payload) for payload in source_payloads],
		"existing_session_charge_keys": list(existing.keys()),
		"submitted_charge_keys": submitted,
		"draft_charge_keys": draft,
		"pending_unbilled_charge_keys": pending,
		"rows": rows,
		"payment_ledger": ledger,
		"linked_invoices": ledger.get("invoices"),
		"aggregate_outstanding": ledger.get("outstanding_amount"),
		"gate_mode": gate.get("gate"),
		"gate_allowed": gate.get("can_proceed"),
		"gate_blocked_reason": None if gate.get("can_proceed") else gate.get("message"),
	}


def get_unbilled_diagnostic_reason(charge, invoice_docstatus) -> str:
	if not charge:
		return "No Billing Session Charge exists for this source detail."
	if invoice_docstatus == 1:
		return "Charge is linked to a submitted Sales Invoice."
	if invoice_docstatus == 0:
		return "Charge is linked to an active draft Sales Invoice."
	if invoice_docstatus == 2:
		return "Charge is linked to a cancelled Sales Invoice and is not draftable unless reset."
	if not charge.get("invoice"):
		return "Charge has no linked invoice and is pending."
	return "Charge invoice state could not be resolved."


def get_billing_session_summary(session) -> dict:
	session = ensure_session_doc(session)
	refresh_billing_session_totals(session)
	ledger = get_billing_session_invoice_ledger(session)
	invoices = ledger["invoices"]
	gate = get_payment_gate_status(session)
	source_documents = list(
		OrderedDict.fromkeys(
			f"{row.source_doctype}:{row.source_name}" for row in session.get("charges") or [] if row.source_doctype and row.source_name
		)
	)
	return {
		"name": session.name,
		"status": session.status,
		"customer": session.customer,
		"animal": session.get("animal"),
		"company": session.get("company"),
		"branch": session.get("branch"),
		"payment_gate_mode": normalize_payment_gate_mode(session.get("payment_gate_mode")),
		"current_draft_invoice": session.get("current_draft_invoice"),
		"latest_invoice": session.get("latest_invoice"),
		"total_charges": flt(session.get("total_charges")),
		"total_invoiced": flt(session.get("total_invoiced")),
		"total_paid": flt(session.get("total_paid")),
		"outstanding_amount": flt(session.get("outstanding_amount")),
		"payment_status": session.get("payment_status"),
		"invoices": invoices,
		"invoice_ledger": ledger,
		"session_warning": get_session_payment_warning(ledger),
		"payment_gate": gate,
		"source_documents": [{"doctype": item.split(":", 1)[0], "name": item.split(":", 1)[1]} for item in source_documents],
		"charges": [serialize_charge(row) for row in session.get("charges") or []],
	}


def get_payment_gate_status(session) -> dict:
	session = ensure_session_doc(session)
	refresh_billing_session_totals(session)
	mode = normalize_payment_gate_mode(session.get("payment_gate_mode"))
	ledger = get_billing_session_invoice_ledger(session)
	if ledger["has_pending_uninvoiced_charges"] and not ledger["invoices"]:
		return {"gate": mode, "can_proceed": False, "status": "Blocked", "message": "A Sales Invoice must be generated before service can proceed."}
	if not ledger["invoices"]:
		return {"gate": mode, "can_proceed": False, "status": "Blocked", "message": "A Sales Invoice must be generated before service can proceed."}
	if mode == NO_PAYMENT_GATE:
		return {
			"gate": mode,
			"can_proceed": True,
			"status": "Allowed",
			"message": get_session_payment_warning(ledger) or "Invoice has been generated. Payment is not required before proceeding.",
		}
	if not ledger["submitted_invoice_count"]:
		return {"gate": mode, "can_proceed": False, "status": "Blocked", "message": "At least one linked Sales Invoice must be submitted before service can proceed."}
	if mode == PARTIAL_PAYMENT_GATE:
		allowed = flt(ledger["total_paid"]) > 0
		message = "Payment gate passed."
		if allowed and ledger["outstanding_amount"] > 0:
			message = get_session_payment_warning(ledger) or message
		return {"gate": mode, "can_proceed": allowed, "status": "Allowed" if allowed else "Blocked", "message": message if allowed else "A partial payment is required before service can proceed."}
	if ledger["has_pending_uninvoiced_charges"]:
		return {"gate": mode, "can_proceed": False, "status": "Blocked", "message": "Full payment required. There are pending uninvoiced charges."}
	if ledger["has_active_draft_invoice"]:
		return {"gate": mode, "can_proceed": False, "status": "Blocked", "message": "Full payment required. There is still an active draft invoice."}
	if ledger["has_unpaid_submitted_invoice"] or flt(ledger["outstanding_amount"]) > 0:
		return {
			"gate": mode,
			"can_proceed": False,
			"status": "Blocked",
			"message": f"Full payment required. {format_money_for_message(ledger['outstanding_amount'], ledger.get('currency'))} is still outstanding across this billing session.",
		}
	allowed = ledger["submitted_invoice_count"] > 0 and flt(ledger["outstanding_amount"]) <= 0
	return {"gate": mode, "can_proceed": allowed, "status": "Allowed" if allowed else "Blocked", "message": "Payment gate passed." if allowed else "Full payment is required before service can proceed."}


def get_session_payment_warning(ledger: dict) -> str | None:
	if flt(ledger.get("outstanding_amount")) > 0:
		return "This billing session still has unpaid balance from earlier invoice(s)."
	return None


def format_money_for_message(amount, currency=None) -> str:
	value = flt(amount)
	if currency == "NGN" or not currency:
		return f"?{value:,.2f}"
	return f"{currency} {value:,.2f}"


def can_proceed_with_payment_gate(session) -> bool:
	return bool(get_payment_gate_status(session).get("can_proceed"))


@frappe.whitelist()
def create_or_update_invoice_for_billing_session(session_name: str, confirm: bool = False, confirmation_type: str | None = None):
	session = frappe.get_doc(BILLING_SESSION_DOCTYPE, session_name)
	session.check_permission("write")
	result = sync_session_charges_to_invoice(session.name, confirm=confirm, confirmation_type=confirmation_type)
	summary = get_billing_session_summary(result.get("session") or session.name)
	result["billing_session"] = summary
	return result


@frappe.whitelist()
def refresh_billing_session_summary(session_name: str):
	session = frappe.get_doc(BILLING_SESSION_DOCTYPE, session_name)
	session.check_permission("write")
	refresh_billing_session_totals(session)
	session.save()
	return get_billing_session_summary(session.name)


@frappe.whitelist()
def get_billing_session_invoice_state(session_name: str):
	session = frappe.get_doc(BILLING_SESSION_DOCTYPE, session_name)
	session.check_permission("read")
	current = get_invoice_docstate(session.get("current_draft_invoice"))
	latest = get_invoice_docstate(session.get("latest_invoice"))
	return {
		"session": session.name,
		"current_draft_invoice": current,
		"latest_invoice": latest,
		"has_pending_charges": bool(_get_pending_charges_for_invoice(session, _get_active_draft_invoice(session))),
	}


def get_invoice_docstate(invoice_name: str | None):
	if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
		return None
	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	return {"name": invoice.name, "docstatus": cint(invoice.docstatus), "status": invoice.get("status")}


def close_billing_session(session):
	session = ensure_session_doc(session)
	refresh_billing_session_totals(session)
	if flt(session.outstanding_amount) > 0:
		frappe.throw("Billing Session cannot be closed while it has an outstanding amount.", frappe.ValidationError)
	session.status = "Closed"
	session.save()
	return session


def cancel_billing_session(session):
	session = ensure_session_doc(session)
	if any(row.get("invoice") and cint(frappe.db.get_value("Sales Invoice", row.invoice, "docstatus")) == 1 for row in session.get("charges") or []):
		frappe.throw("Billing Session cannot be cancelled because it has submitted invoices.", frappe.ValidationError)
	session.status = "Cancelled"
	session.save()
	return session


def sync_source_to_billing_session(source_doctype: str, source_name: str, confirm: bool = False, confirmation_type: str | None = None):
	session = sync_source_charge_payloads_to_billing_session(source_doctype, source_name)
	result = sync_session_charges_to_invoice(session.name, confirm=confirm, confirmation_type=confirmation_type)
	summary = get_billing_session_summary(result.get("session") or session.name)
	update_all_session_source_compatibility_fields(summary)
	result["session"] = summary.get("name")
	return result


def sync_source_charge_payloads_to_billing_session(source_doctype: str, source_name: str):
	"""Persist current source charge payloads without creating or updating an invoice."""
	session = get_or_create_billing_session(source_doctype, source_name, payment_gate_mode=get_source_payment_gate_mode(source_doctype))
	if should_sync_related_billable_sources_to_session():
		sync_all_related_sources_to_billing_session(session, source_doctype, source_name)
	else:
		sync_single_source_to_billing_session(session, source_doctype, source_name)
	return ensure_session_doc(session.name)


def sync_single_source_to_billing_session(session, source_doctype: str, source_name: str):
	session = ensure_session_doc(session)
	payloads = get_source_charge_payloads(source_doctype, source_name, session)
	for payload in payloads:
		add_or_update_session_charge(session, payload)
	retire_missing_source_charges(session, source_doctype, source_name, payloads)
	session.save()
	return session


def sync_all_related_sources_to_billing_session(session, trigger_source_doctype=None, trigger_source_name=None):
	session = ensure_session_doc(session)
	for source_doctype, source_name in find_related_billable_sources_for_session(session, trigger_source_doctype, trigger_source_name):
		if source_doctype and source_name:
			payloads = get_source_charge_payloads(source_doctype, source_name, session)
			for payload in payloads:
				add_or_update_session_charge(session, payload)
			retire_missing_source_charges(session, source_doctype, source_name, payloads)
	session.save()
	return session


def retire_missing_source_charges(session, source_doctype: str, source_name: str, active_payloads: list[dict]) -> int:
	active_keys = {payload.get("charge_key") or build_charge_key(payload) for payload in active_payloads}
	retired = 0
	for row in session.get("charges") or []:
		if row.get("source_doctype") != source_doctype or row.get("source_name") != source_name:
			continue
		if row.get("charge_key") in active_keys:
			continue
		if is_charge_already_submitted(row) or row.get("billing_status") in {"Submitted Invoiced", "Paid"}:
			continue
		if row.get("billing_status") != "Cancelled":
			row.billing_status = "Cancelled"
			retired += 1
	return retired


def remove_retired_charge_items_from_draft_invoice(session, invoice) -> int:
	if not invoice or cint(invoice.get("docstatus")) != 0:
		return 0
	retired_keys = {
		row.get("charge_key")
		for row in session.get("charges") or []
		if row.get("invoice") == invoice.name and row.get("billing_status") in {"Cancelled", "Skipped"}
	}
	if not retired_keys:
		return 0
	kept = []
	removed = 0
	for row in invoice.get("items") or []:
		if extract_charge_key_from_invoice_item(row) in retired_keys:
			removed += 1
			continue
		kept.append(row)
	invoice.items = kept
	for row in session.get("charges") or []:
		if row.get("charge_key") in retired_keys:
			row.invoice_item_name = None
	return removed


def remove_empty_draft_invoice_for_session(session, invoice, removed_count: int = 0) -> dict:
	if not invoice or cint(invoice.get("docstatus")) != 0:
		frappe.throw("Only draft Sales Invoices can be removed by this action.", frappe.ValidationError)
	if invoice.get("items"):
		frappe.throw("Draft Sales Invoice still has items and cannot be removed as empty.", frappe.ValidationError)
	invoice_name = invoice.name
	session = detach_invoice_from_billing_session(session, invoice_name, reason="empty_draft_invoice")
	detach_invoice_from_vetedge_sources(invoice_name, reason="empty_draft_invoice", session=session)
	run_with_billing_core_sync_flag(lambda: frappe.delete_doc("Sales Invoice", invoice_name))
	refresh_billing_session_totals(session)
	session.save()
	return {
		"session": session.name,
		"billing_session": session.name,
		"invoice": invoice_name,
		"created": False,
		"added_count": 0,
		"updated_count": 0,
		"removed_count": removed_count,
		"removed_empty_invoice": True,
		"message": f"Empty draft invoice {invoice_name} removed.",
		"reload_required": True,
	}


def detach_invoice_from_billing_session(session, invoice_name: str, *, reason: str | None = None):
	session = ensure_session_doc(session.name if hasattr(session, "name") else session)
	if session.get("current_draft_invoice") == invoice_name:
		session.current_draft_invoice = None
	if session.get("latest_invoice") == invoice_name:
		session.latest_invoice = get_latest_existing_session_invoice_name(session, exclude=invoice_name)
	for row in session.get("charges") or []:
		if row.get("invoice") == invoice_name:
			row.invoice = None
			row.invoice_item_name = None
			if reason and row.get("billing_status") not in {"Cancelled", "Skipped"}:
				row.notes = "; ".join(part for part in [row.get("notes"), f"Detached invoice: {reason}"] if part)
	session.save()
	return session


def detach_invoice_from_vetedge_sources(invoice_name: str, *, reason: str | None = None, session=None) -> list[dict]:
	"""Clear cleanup-safe VetEdge source links before Sales Invoice delete/cancel."""
	detached: list[dict] = []
	for doctype, config in SAFE_SOURCE_INVOICE_LINK_FIELDS.items():
		if not safe_doctype_exists(doctype):
			continue
		fieldname = config.get("field")
		if not fieldname or not safe_meta_has_field(doctype, fieldname):
			continue
		for row in frappe.get_all(doctype, filters={fieldname: invoice_name}, fields=["name"]):
			values = {fieldname: None}
			status_field = config.get("status_field")
			if status_field and safe_meta_has_field(doctype, status_field):
				values[status_field] = config.get("empty_status")
			for key, value in (config.get("extra_values") or {}).items():
				if safe_meta_has_field(doctype, key):
					values[key] = value
			frappe.db.set_value(doctype, row.name, values, update_modified=False)
			detached.append({"doctype": doctype, "name": row.name, "field": fieldname})

	for child_doctype, config in SAFE_SOURCE_INVOICE_CHILD_LINK_FIELDS.items():
		if not safe_doctype_exists(child_doctype):
			continue
		fieldname = config.get("field")
		if not fieldname or not safe_meta_has_field(child_doctype, fieldname):
			continue
		fields = ["name"]
		meta = frappe.get_meta(child_doctype)
		for child_field in ("parent", "parenttype", "parentfield"):
			if meta.has_field(child_field):
				fields.append(child_field)
		for row in frappe.get_all(child_doctype, filters={fieldname: invoice_name}, fields=fields):
			if config.get("action") == "delete":
				run_with_billing_core_sync_flag(lambda row_name=row.name, doctype=child_doctype: frappe.delete_doc(doctype, row_name))
			else:
				values = {fieldname: None}
				for key, value in (config.get("extra_values") or {}).items():
					if safe_meta_has_field(child_doctype, key):
						values[key] = value
				frappe.db.set_value(child_doctype, row.name, values, update_modified=False)
			detached.append({"doctype": child_doctype, "name": row.name, "field": fieldname})
	return detached


def safe_doctype_exists(doctype: str) -> bool:
	try:
		return bool(frappe.db.exists("DocType", doctype))
	except Exception:
		return False


def safe_meta_has_field(doctype: str, fieldname: str) -> bool:
	try:
		meta = frappe.get_meta(doctype)
		return bool(meta.has_field(fieldname) or fieldname in {"name", "parent", "parenttype", "parentfield"})
	except Exception:
		return False


def get_latest_existing_session_invoice_name(session, exclude: str | None = None) -> str | None:
	for name in reversed(get_session_invoice_names(session)):
		if name and name != exclude and name != session.get("current_draft_invoice") and frappe.db.exists("Sales Invoice", name):
			return name
	return None


def get_retired_submitted_invoice_action(session, confirm: bool = False, confirmation_type: str | None = None) -> dict | None:
	retired_by_invoice = {}
	active_by_invoice = {}
	for row in session.get("charges") or []:
		invoice_name = row.get("invoice")
		if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
			continue
		if cint(frappe.db.get_value("Sales Invoice", invoice_name, "docstatus")) != 1:
			continue
		if row.get("billing_status") in {"Cancelled", "Skipped"}:
			retired_by_invoice.setdefault(invoice_name, []).append(row)
		else:
			active_by_invoice.setdefault(invoice_name, []).append(row)
	for invoice_name in retired_by_invoice:
		if active_by_invoice.get(invoice_name):
			return {
				"blocked": True,
				"reason": "submitted_invoice_has_active_charges",
				"invoice": invoice_name,
				"message": "This submitted invoice still has active charges. Create an adjustment charge instead.",
				"reload_required": True,
			}
		state = get_invoice_payment_state(invoice_name)
		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		paid = flt(state.get("paid_amount"))
		outstanding = flt(state.get("outstanding_amount"))
		total = flt(invoice.get("grand_total"))
		if paid > 0 or outstanding < total:
			return {
				"blocked": True,
				"reason": "paid_invoice_requires_credit_note",
				"invoice": invoice_name,
				"billing_session": session.name,
				"message": "This invoice is paid or partly paid. Create a Credit Note or adjustment instead.",
				"reload_required": True,
			}
		if not (confirm and confirmation_type == "cancel_unpaid_invoice"):
			return {
				"requires_confirmation": True,
				"confirmation_type": "cancel_unpaid_invoice",
				"invoice": invoice_name,
				"billing_session": session.name,
				"message": "This submitted unpaid invoice must be cancelled before removing invoiced charges.",
				"reload_required": True,
			}
		session = detach_invoice_from_billing_session(session, invoice_name, reason="cancel_unpaid_invoice")
		detach_invoice_from_vetedge_sources(invoice_name, reason="cancel_unpaid_invoice", session=session)
		run_with_billing_core_sync_flag(invoice.cancel)
		for row in retired_by_invoice[invoice_name]:
			row.billing_status = "Cancelled"
			row.invoice_item_name = None
		refresh_billing_session_totals(session)
		session.save()
		return {
			"removed_empty_invoice": False,
			"cancelled_invoice": True,
			"invoice": invoice_name,
			"session": session.name,
			"billing_session": session.name,
			"message": f"Cancelled unpaid invoice {invoice_name}.",
			"reload_required": True,
		}
	return None



def run_with_billing_core_sync_flag(fn):
	flags = getattr(frappe, "flags", None)
	if flags is None:
		return fn()
	previous = getattr(flags, "vetedge_billing_core_syncing", False)
	flags.vetedge_billing_core_syncing = True
	try:
		return fn()
	finally:
		flags.vetedge_billing_core_syncing = previous


def safe_refresh_billing_session(session_name: str, reconcile: bool = False):
	if not session_name or not frappe.db.exists(BILLING_SESSION_DOCTYPE, session_name):
		return None
	session = frappe.get_doc(BILLING_SESSION_DOCTYPE, session_name)
	if reconcile:
		reconcile_session_charge_statuses(session)
	refresh_billing_session_totals(session)
	session.save()
	return session


def update_session_after_invoice_sync(session_name: str, invoice_name: str, charge_keys: list[str]):
	session = frappe.get_doc(BILLING_SESSION_DOCTYPE, session_name)
	for row in session.get("charges") or []:
		if row.get("charge_key") in charge_keys:
			row.invoice = invoice_name
			row.billing_status = "Draft Invoiced"
	session.current_draft_invoice = invoice_name
	session.latest_invoice = invoice_name
	refresh_billing_session_totals(session)
	session.save()
	return session


def find_related_billable_sources_for_session(session, trigger_source_doctype=None, trigger_source_name=None) -> list[tuple[str, str]]:
	session = ensure_session_doc(session)
	sources = OrderedDict()

	def add(doctype, name):
		if doctype in SUPPORTED_BILLING_SOURCE_DOCTYPES and name:
			sources[(doctype, name)] = None

	add(trigger_source_doctype, trigger_source_name)
	add(session.get("created_from_doctype"), session.get("created_from_name"))
	if session.get("source_context_doctype") in SUPPORTED_BILLING_SOURCE_DOCTYPES:
		add(session.get("source_context_doctype"), session.get("source_context_name"))

	identity = get_session_billing_identity(session, trigger_source_doctype, trigger_source_name)
	consultation = identity.get("consultation") or find_active_consultation_for_identity(identity)
	patient = identity.get("patient") or session.get("animal")
	customer = identity.get("customer") or session.get("customer")

	if trigger_source_doctype == "Veterinary Patient" and trigger_source_name:
		add("Veterinary Patient", trigger_source_name)
	if consultation:
		add("Veterinary Consultation", consultation)
		add_linked_sources("Veterinary Lab Order", "consultation", consultation, add)
		add_linked_sources("Veterinary Vaccination Record", "linked_consultation", consultation, add)
		add_linked_sources("Veterinary Hospitalisation", "linked_consultation", consultation, add)

	# Grooming and boarding are not visit-scoped in current metadata; only include them when directly triggered/created.
	return list(sources.keys())


def add_linked_sources(doctype: str, fieldname: str, value: str, add):
	if not value or not frappe.db.exists("DocType", doctype) or not doctype_has_field(doctype, fieldname):
		return
	filters = {fieldname: value}
	if doctype_has_field(doctype, "status"):
		filters["status"] = ["!=", "Cancelled"]
	for row in frappe.get_all(doctype, filters=filters, fields=["name"]):
		add(doctype, row.name)


def get_session_billing_identity(session, trigger_source_doctype=None, trigger_source_name=None) -> dict:
	identity = frappe._dict(patient=session.get("animal"), customer=session.get("customer"), branch=session.get("branch"), company=session.get("company"))
	if trigger_source_doctype and trigger_source_name:
		identity.update(get_source_billing_identity(trigger_source_doctype, trigger_source_name))
	return identity


def get_source_billing_identity(source_doctype: str, source_name: str, doc=None) -> dict:
	if not source_doctype or not source_name:
		return frappe._dict()
	doc = doc or frappe.get_doc(source_doctype, source_name)
	patient = doc.get("patient") or doc.get("animal") or (doc.name if source_doctype == "Veterinary Patient" else None)
	customer = doc.get("primary_owner") or doc.get("customer")
	return frappe._dict(
		patient=patient,
		customer=customer,
		branch=doc.get("service_branch") or doc.get("branch") or doc.get("default_branch"),
		company=doc.get("company"),
		consultation=doc.get("consultation") or doc.get("linked_consultation") or (doc.name if source_doctype == "Veterinary Consultation" else None),
	)


def find_active_consultation_for_identity(identity: dict | None) -> str | None:
	identity = identity or {}
	patient = identity.get("patient")
	customer = identity.get("customer")
	if not patient or not frappe.db.exists("DocType", "Veterinary Consultation"):
		return None
	filters = {"patient": patient}
	if customer and doctype_has_field("Veterinary Consultation", "primary_owner"):
		filters["primary_owner"] = customer
	if doctype_has_field("Veterinary Consultation", "status"):
		filters["status"] = ["not in", ["Cancelled", "Completed"]]
	rows = frappe.get_all("Veterinary Consultation", filters=filters, fields=["name"], order_by="creation asc", limit=1)
	return rows[0].name if rows else None


def doctype_has_field(doctype: str, fieldname: str) -> bool:
	try:
		return bool(frappe.get_meta(doctype).has_field(fieldname))
	except Exception:
		return False


def get_source_charge_payloads(source_doctype: str, source_name: str, session=None) -> list[dict]:
	if source_doctype == "Veterinary Consultation":
		return get_consultation_charge_payloads(source_name, session)
	if source_doctype == "Veterinary Lab Order":
		return get_lab_order_charge_payloads(source_name, session)
	if source_doctype == "Veterinary Hospitalisation":
		return get_hospitalisation_charge_payloads(source_name, session)
	if source_doctype == "Veterinary Vaccination Record":
		return get_vaccination_charge_payloads(source_name, session)
	if source_doctype == "Veterinary Patient":
		return get_patient_registration_charge_payloads(source_name, session)
	if source_doctype == "Pet Grooming Session":
		return get_grooming_charge_payloads(source_name, session)
	if source_doctype == "Pet Boarding Booking":
		return get_boarding_charge_payloads(source_name, session)
	return []


def consultation_to_billing_charges(doc) -> list[dict]:
	return get_consultation_charge_payloads(doc.name)


def lab_order_to_billing_charges(doc) -> list[dict]:
	return build_lab_payloads(doc, get_billing_cost_center(doc.service_branch, required=True))


def vaccination_to_billing_charges(doc) -> list[dict]:
	item_code = frappe.db.get_value("Veterinary Vaccine", doc.get("vaccine"), "default_item") if doc.get("vaccine") else None
	if not item_code:
		return []
	cost_center = get_billing_cost_center(doc.service_branch, required=True)
	return [build_source_charge(doc, "Vaccination", doc.name, item_code, 1, None, None, cost_center)]


def registration_to_billing_charges(doc) -> list[dict]:
	return get_patient_registration_charge_payloads(doc.name)


def hospitalisation_to_billing_charges(doc) -> list[dict]:
	return get_hospitalisation_charge_payloads(doc.name)


def grooming_to_billing_charges(doc) -> list[dict]:
	return build_grooming_payloads(doc)


def boarding_to_billing_charges(doc) -> list[dict]:
	return build_boarding_payloads(doc)


def refresh_billing_session_totals(session):
	session = ensure_session_doc(session)
	ledger = get_billing_session_invoice_ledger(session)
	session.total_charges = ledger["total_charges"]
	session.total_invoiced = ledger["total_invoiced"]
	session.total_paid = ledger["total_paid"]
	session.outstanding_amount = ledger["outstanding_amount"]
	session.payment_status = ledger["payment_status"]
	session.billing_summary_json = json.dumps(
		{
			"invoice_count": len(ledger["invoices"]),
			"submitted_invoice_count": ledger["submitted_invoice_count"],
			"draft_invoice_count": ledger["draft_invoice_count"],
			"cancelled_invoice_count": ledger["cancelled_invoice_count"],
			"total_charges": ledger["total_charges"],
			"total_invoiced": ledger["total_invoiced"],
			"total_submitted": ledger["total_submitted"],
			"total_draft": ledger["total_draft"],
			"total_paid": ledger["total_paid"],
			"outstanding_amount": ledger["outstanding_amount"],
			"has_pending_uninvoiced_charges": ledger["has_pending_uninvoiced_charges"],
		},
		default=str,
	)
	if session.status not in {"Closed", "Cancelled"}:
		if ledger["payment_status"] == "Paid":
			session.status = "Paid"
		elif ledger["total_paid"] > 0:
			session.status = "Partially Paid"
		else:
			session.status = "Active"
	return session


def get_billing_session_invoice_ledger(session) -> dict:
	session = ensure_session_doc(session)
	invoice_rows = []
	invoice_names = get_session_invoice_names(session)
	total_charges = sum(flt(row.amount) for row in session.get("charges") or [] if row.get("billing_status") not in {"Cancelled", "Skipped"})
	has_pending_uninvoiced_charges = any(
		(not row.get("invoice") and row.get("billing_status") not in {"Cancelled", "Skipped"})
		or row.get("billing_status") == "Pending"
		for row in session.get("charges") or []
	)
	total_invoiced = total_submitted = total_draft = total_paid = outstanding_amount = 0
	draft_invoice_count = submitted_invoice_count = unpaid_invoice_count = cancelled_invoice_count = 0
	has_unpaid_submitted_invoice = has_active_draft_invoice = False
	currency = None

	for invoice_name in invoice_names:
		if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
			continue
		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		docstatus = cint(invoice.docstatus)
		grand_total = flt(invoice.get("grand_total"))
		rounded_total = flt(invoice.get("rounded_total"))
		invoice_total = rounded_total or grand_total
		paid_amount = flt(invoice.get("paid_amount"))
		invoice_outstanding = flt(invoice.get("outstanding_amount"))
		if docstatus == 1:
			state = get_invoice_payment_state(invoice.name)
			paid_amount = flt(state.get("paid_amount"))
			invoice_outstanding = flt(state.get("outstanding_amount"))
		if not currency:
			currency = invoice.get("currency")
		is_cancelled = docstatus == 2
		is_draft = docstatus == 0
		is_submitted = docstatus == 1
		contributes = not is_cancelled
		blocks_full_payment_gate = False
		if is_draft:
			draft_invoice_count += 1
			has_active_draft_invoice = True
			blocks_full_payment_gate = True
		elif is_submitted:
			submitted_invoice_count += 1
			if invoice_outstanding > 0:
				unpaid_invoice_count += 1
				has_unpaid_submitted_invoice = True
				blocks_full_payment_gate = True
		elif is_cancelled:
			cancelled_invoice_count += 1
		if contributes:
			total_invoiced += invoice_total
			if is_draft:
				total_draft += invoice_total
			elif is_submitted:
				total_submitted += invoice_total
				total_paid += paid_amount
				outstanding_amount += invoice_outstanding
		invoice_rows.append(
			{
				"invoice": invoice.name,
				"name": invoice.name,
				"docstatus": docstatus,
				"status": invoice.get("status"),
				"grand_total": grand_total,
				"rounded_total": rounded_total,
				"paid_amount": paid_amount,
				"outstanding_amount": invoice_outstanding,
				"currency": invoice.get("currency"),
				"is_draft": is_draft,
				"is_submitted": is_submitted,
				"is_cancelled": is_cancelled,
				"blocks_full_payment_gate": blocks_full_payment_gate,
				"contributes_to_total": contributes,
			}
		)

	payment_status = get_session_payment_status_from_ledger(
		submitted_invoice_count=submitted_invoice_count,
		draft_invoice_count=draft_invoice_count,
		has_pending_uninvoiced_charges=has_pending_uninvoiced_charges,
		outstanding_amount=outstanding_amount,
		total_paid=total_paid,
	)
	return {
		"invoices": invoice_rows,
		"total_charges": flt(total_charges),
		"total_invoiced": flt(total_invoiced),
		"total_submitted": flt(total_submitted),
		"total_draft": flt(total_draft),
		"total_paid": flt(total_paid),
		"outstanding_amount": flt(outstanding_amount),
		"draft_invoice_count": draft_invoice_count,
		"submitted_invoice_count": submitted_invoice_count,
		"unpaid_invoice_count": unpaid_invoice_count,
		"cancelled_invoice_count": cancelled_invoice_count,
		"has_unpaid_submitted_invoice": has_unpaid_submitted_invoice,
		"has_active_draft_invoice": has_active_draft_invoice,
		"has_pending_uninvoiced_charges": has_pending_uninvoiced_charges,
		"payment_status": payment_status,
		"currency": currency,
	}


def get_session_payment_status_from_ledger(
	*,
	submitted_invoice_count: int,
	draft_invoice_count: int,
	has_pending_uninvoiced_charges: bool,
	outstanding_amount: float,
	total_paid: float,
) -> str:
	if not submitted_invoice_count and not draft_invoice_count:
		return "Pending Invoice" if has_pending_uninvoiced_charges else "Not Invoiced"
	if draft_invoice_count:
		return "Draft Invoice Pending"
	if has_pending_uninvoiced_charges:
		return "Pending Invoice"
	if submitted_invoice_count and flt(outstanding_amount) > 0 and flt(total_paid) > 0:
		return "Partially Paid"
	if submitted_invoice_count and flt(outstanding_amount) > 0:
		return "Unpaid"
	if submitted_invoice_count and flt(outstanding_amount) <= 0:
		return "Paid"
	return "Not Invoiced"


def update_billing_sessions_from_invoice(doc, method: str | None = None) -> None:
	if not is_billing_sessions_enabled() or getattr(frappe.flags, "vetedge_billing_core_syncing", False):
		return
	for session_name in get_sessions_for_invoice(doc.name):
		safe_refresh_billing_session(session_name, reconcile=True)


def update_billing_sessions_from_payment_entry(doc, method: str | None = None) -> None:
	if not is_billing_sessions_enabled() or getattr(frappe.flags, "vetedge_billing_core_syncing", False):
		return
	invoice_names = [
		row.reference_name
		for row in doc.get("references") or []
		if row.reference_doctype == "Sales Invoice" and row.reference_name
	]
	for invoice_name in invoice_names:
		for session_name in get_sessions_for_invoice(invoice_name):
			safe_refresh_billing_session(session_name)


def get_sessions_for_invoice(invoice_name: str) -> list[str]:
	names = []
	rows = frappe.get_all(BILLING_SESSION_CHARGE_DOCTYPE, filters={"invoice": invoice_name}, fields=["parent"])
	for row in rows:
		if row.parent not in names:
			names.append(row.parent)
	rows = frappe.get_all(
		BILLING_SESSION_DOCTYPE,
		filters=[["current_draft_invoice", "=", invoice_name], ["name", "not in", names]],
		fields=["name"],
	)
	names.extend(row.name for row in rows)
	rows = frappe.get_all(
		BILLING_SESSION_DOCTYPE,
		filters=[["latest_invoice", "=", invoice_name], ["name", "not in", names]],
		fields=["name"],
	)
	names.extend(row.name for row in rows)
	return names


def get_source_context(source_doctype: str, source_name: str) -> tuple[str, str]:
	if source_uses_explicit_billing_session(source_doctype) and source_name:
		session_name = frappe.db.get_value(source_doctype, source_name, "billing_session")
		if session_name:
			return BILLING_SESSION_DOCTYPE, session_name
	if source_doctype == "Veterinary Lab Order":
		consultation = frappe.db.get_value(source_doctype, source_name, "consultation")
		if consultation:
			return "Veterinary Consultation", consultation
	if source_doctype == "Veterinary Hospitalisation":
		consultation = frappe.db.get_value(source_doctype, source_name, "linked_consultation")
		if consultation:
			return "Veterinary Consultation", consultation
	if source_doctype == "Veterinary Vaccination Record":
		consultation = frappe.db.get_value(source_doctype, source_name, "linked_consultation")
		if consultation:
			return "Veterinary Consultation", consultation
	return source_doctype, source_name


def source_uses_explicit_billing_session(source_doctype: str) -> bool:
	try:
		return frappe.get_meta(source_doctype).has_field("billing_session")
	except Exception:
		return False


def get_source_payment_gate_mode(source_doctype: str) -> str:
	if source_doctype == "Veterinary Consultation":
		from vetedge.services.payment_gate import get_consultation_payment_gate

		return normalize_payment_gate_mode(get_consultation_payment_gate())
	if source_doctype == "Veterinary Hospitalisation":
		from vetedge.services.hospitalisation import get_hospitalisation_payment_gate

		return normalize_payment_gate_mode(get_hospitalisation_payment_gate())
	return normalize_payment_gate_mode(None)


def get_consultation_charge_payloads(consultation_name: str, session=None) -> list[dict]:
	from vetedge.services.billing import get_consultation_billing_settings

	doc = frappe.get_doc("Veterinary Consultation", consultation_name)
	settings = get_consultation_billing_settings()
	if not settings.enabled:
		return []
	cost_center = get_billing_cost_center(doc.service_branch, required=True)
	payloads = []
	if settings.consultation_item:
		payloads.append(build_source_charge(doc, "Consultation Fee", doc.name, settings.consultation_item, 1, None, None, cost_center))
	registration_payload = get_registration_charge_payload_for_consultation(doc, session)
	if registration_payload:
		payloads.append(registration_payload)
	if settings.enable_treatment_billing:
		for row in doc.get("planned_treatments") or []:
			if row.get("item"):
				payloads.append(build_source_charge(doc, "Treatment", row.get("name") or f"{row.item}:{row.get('idx') or 0}", row.item, row.get("qty"), row.get("uom"), row.get("rate"), cost_center, row.get("description")))
	payloads.extend(get_lab_order_charge_payloads_for_consultation(doc.name, cost_center))
	payloads.extend(get_vaccination_charge_payloads_for_consultation(doc.name, cost_center))
	return payloads



def should_include_registration_charge_for_consultation(consultation_doc, session) -> bool:
	patient = consultation_doc.get("patient")
	if not patient:
		return False
	try:
		from vetedge.services.registration_billing import get_registration_rule, is_first_consultation_for_patient
	except Exception:
		return False

	branch = consultation_doc.get("service_branch") or frappe.db.get_value("Veterinary Patient", patient, "default_branch")
	rule = get_registration_rule(branch)
	if not rule.enabled or not rule.require_payment_before_first_consultation:
		return False
	if not is_first_consultation_for_patient(patient, current_consultation=consultation_doc.name):
		return False
	if is_patient_registration_fee_paid(patient, consultation_doc.get("primary_owner")):
		return False
	charge_key = get_registration_charge_key(patient)
	if session and get_session_charge(ensure_session_doc(session), charge_key):
		return False
	return True


def get_registration_charge_payload_for_consultation(consultation_doc, session):
	if not should_include_registration_charge_for_consultation(consultation_doc, session):
		return None
	from vetedge.services.registration_billing import get_registration_rule

	patient = frappe.get_doc("Veterinary Patient", consultation_doc.patient)
	branch = consultation_doc.get("service_branch") or patient.get("default_branch")
	rule = get_registration_rule(branch)
	if not rule.registration_item:
		return None
	cost_center = get_billing_cost_center(branch, required=rule.enforce_cost_center)
	payload = build_source_charge(
		patient,
		"Registration Fee",
		patient.name,
		rule.registration_item,
		1,
		None,
		rule.registration_fee,
		cost_center,
		description="Registration Fee",
	)
	payload["charge_key"] = get_registration_charge_key(patient.name)
	payload["source_detail_name"] = "Registration Fee"
	payload["branch"] = branch
	return payload


def get_registration_charge_key(patient: str) -> str:
	return f"Veterinary Patient:{patient}:Registration Fee"


def is_patient_registration_fee_paid(patient, customer=None) -> bool:
	if not patient or not frappe.db.exists("Veterinary Patient", patient):
		return False
	patient_doc = frappe.db.get_value(
		"Veterinary Patient",
		patient,
		["primary_owner", "registration_status", "registration_invoice"],
		as_dict=True,
	)
	if not patient_doc:
		return False
	if customer and patient_doc.get("primary_owner") and patient_doc.get("primary_owner") != customer:
		return False
	if patient_doc.get("registration_status") == "Registration Paid":
		return True
	invoice_name = patient_doc.get("registration_invoice")
	if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
		return False
	invoice = frappe.db.get_value("Sales Invoice", invoice_name, ["docstatus", "status", "outstanding_amount"], as_dict=True)
	return bool(invoice and cint(invoice.get("docstatus")) == 1 and (invoice.get("status") == "Paid" or flt(invoice.get("outstanding_amount")) <= 0))


def get_lab_order_charge_payloads(lab_order_name: str, session=None) -> list[dict]:
	order = frappe.get_doc("Veterinary Lab Order", lab_order_name)
	cost_center = get_billing_cost_center(order.service_branch, required=True)
	return build_lab_payloads(order, cost_center)


def get_lab_order_charge_payloads_for_consultation(consultation_name: str, cost_center: str) -> list[dict]:
	if not frappe.db.exists("DocType", "Veterinary Lab Order"):
		return []
	payloads = []
	for row in frappe.get_all("Veterinary Lab Order", filters={"consultation": consultation_name, "status": ["!=", "Cancelled"]}, fields=["name"]):
		payloads.extend(build_lab_payloads(frappe.get_doc("Veterinary Lab Order", row.name), cost_center))
	return payloads


def build_lab_payloads(order, cost_center: str) -> list[dict]:
	payloads = []
	for row in order.get("lab_tests") or []:
		if not row.get("billing_item"):
			continue
		rate = frappe.db.get_value("Veterinary Lab Test", row.lab_test_template, "default_rate")
		payloads.append(build_source_charge(order, "Lab", row.get("name") or row.lab_test_template, row.billing_item, 1, None, rate, cost_center, row.get("lab_test_name") or row.lab_test_template))
	return payloads


def get_hospitalisation_charge_payloads(hospitalisation_name: str, session=None) -> list[dict]:
	from vetedge.services.hospitalisation import build_hospitalisation_charge_items

	build_hospitalisation_charge_items(hospitalisation_name)
	doc = frappe.get_doc("Veterinary Hospitalisation", hospitalisation_name)
	cost_center = get_billing_cost_center(doc.service_branch, required=True)
	payloads = []
	for row in doc.get("charge_items") or []:
		if row.get("billing_status") == "Cancelled" or not row.get("item"):
			continue
		payloads.append(build_source_charge(doc, "Hospitalisation", row.get("source_hash") or row.get("source_activity"), row.item, row.get("qty"), row.get("uom"), row.get("rate"), cost_center, row.get("description"), source_detail_name=row.get("source_activity"), notes=row.get("notes")))
	return payloads


def get_vaccination_charge_payloads(vaccination_name: str, session=None) -> list[dict]:
	doc = frappe.get_doc("Veterinary Vaccination Record", vaccination_name)
	item_code = frappe.db.get_value("Veterinary Vaccine", doc.get("vaccine"), "default_item") if doc.get("vaccine") else None
	if not item_code:
		return []
	cost_center = get_billing_cost_center(doc.service_branch, required=True)
	return [build_source_charge(doc, "Vaccination", doc.name, item_code, 1, None, None, cost_center)]


def get_vaccination_charge_payloads_for_consultation(consultation_name: str, cost_center: str) -> list[dict]:
	if not frappe.db.exists("DocType", "Veterinary Vaccination Record"):
		return []
	payloads = []
	for row in frappe.get_all("Veterinary Vaccination Record", filters={"linked_consultation": consultation_name, "status": ["!=", "Cancelled"]}, fields=["name", "vaccine"]):
		item_code = frappe.db.get_value("Veterinary Vaccine", row.vaccine, "default_item")
		if item_code:
			doc = frappe._dict(doctype="Veterinary Vaccination Record", name=row.name, service_branch=None)
			payloads.append(build_source_charge(doc, "Vaccination", row.name, item_code, 1, None, None, cost_center))
	return payloads


def get_patient_registration_charge_payloads(patient_name: str, session=None) -> list[dict]:
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return []
	settings = frappe.get_single("Veterinary Settings")
	meta = frappe.get_meta("Veterinary Settings")
	if not meta.has_field("default_registration_item") or not settings.get("default_registration_item"):
		return []
	patient = frappe.get_doc("Veterinary Patient", patient_name)
	cost_center = get_billing_cost_center(patient.get("default_branch"), required=True)
	payload = build_source_charge(patient, "Registration Fee", patient.name, settings.default_registration_item, 1, None, settings.get("default_registration_fee"), cost_center, description="Registration Fee")
	payload["charge_key"] = get_registration_charge_key(patient.name)
	payload["source_detail_name"] = "Registration Fee"
	return [payload]


def get_grooming_charge_payloads(session_name: str, session=None) -> list[dict]:
	doc = frappe.get_doc("Pet Grooming Session", session_name)
	return build_grooming_payloads(doc)


def build_grooming_payloads(doc) -> list[dict]:
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return []
	meta = frappe.get_meta("Veterinary Settings")
	if meta.has_field("enable_grooming_billing") and not cint(frappe.db.get_single_value("Veterinary Settings", "enable_grooming_billing")):
		return []
	if not doc.get("grooming_service"):
		return []
	service = frappe.db.get_value("Pet Grooming Service", doc.grooming_service, ["default_item", "default_rate"], as_dict=True) or {}
	item_code = service.get("default_item")
	if not item_code:
		return []
	cost_center = get_billing_cost_center(doc.service_branch, required=True)
	return [
		build_source_charge(
			doc,
			"Grooming",
			doc.grooming_service,
			item_code,
			1,
			None,
			service.get("default_rate"),
			cost_center,
			description=f"Grooming service: {doc.grooming_service}",
		)
	]


def get_boarding_charge_payloads(booking_name: str, session=None) -> list[dict]:
	doc = frappe.get_doc("Pet Boarding Booking", booking_name)
	return build_boarding_payloads(doc)


def build_boarding_payloads(doc) -> list[dict]:
	item_code = doc.get("billing_item") or get_default_boarding_billing_item()
	if not item_code:
		return []
	qty, rate, amount = get_boarding_charge_values(doc)
	if amount <= 0:
		return []
	cost_center = get_billing_cost_center(doc.service_branch, required=True)
	return [
		build_source_charge(
			doc,
			"Boarding",
			get_boarding_charge_detail_key(doc),
			item_code,
			qty,
			None,
			rate,
			cost_center,
			description=f"Boarding stay charges for {doc.name}",
		)
	]


def get_default_boarding_billing_item() -> str | None:
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return None
	return frappe.db.get_single_value("Veterinary Settings", "default_boarding_billing_item")


def get_boarding_charge_values(doc) -> tuple[float, float, float]:
	qty = flt(doc.get("billable_days"))
	rate = flt(doc.get("daily_rate"))
	amount = flt(doc.get("total_boarding_charge"))
	if amount and qty and not rate:
		rate = amount / qty
	if qty and rate and not amount:
		amount = qty * rate
	if not qty and amount:
		qty = 1
		rate = amount
	return qty, rate, amount


def get_boarding_charge_detail_key(doc) -> str:
	parts = [doc.get("linked_stay"), doc.get("check_in_date"), doc.get("actual_check_out_date"), doc.get("billable_days")]
	return ":".join(str(part) for part in parts if part) or doc.name


def build_source_charge(doc, source_type, source_detail, item_code, qty, uom, rate, cost_center, description=None, source_detail_name=None, notes=None):
	item = frappe.db.get_value("Item", item_code, ["item_name", "stock_uom", "standard_rate"], as_dict=True) or {}
	qty = flt(qty) or 1
	company = get_source_charge_company(doc)
	customer = doc.get("primary_owner") or doc.get("customer")
	branch = doc.get("service_branch") or doc.get("branch") or doc.get("default_branch")
	resolved_uom = uom or item.get("stock_uom")
	posting_date = doc.get("posting_date") or doc.get("transaction_date") or doc.get("consultation_date") or _safe_nowdate()
	rate = flt(rate)
	if rate <= 0:
		rate = flt(
			_get_item_selling_rate(
				item_code,
				company=company,
				customer=customer,
				branch=branch,
				posting_date=posting_date,
				uom=resolved_uom,
			)
		)
	if rate <= 0:
		rate = flt(item.get("standard_rate"))
	amount = flt(qty * rate)
	return {
		"source_doctype": doc.doctype,
		"source_name": doc.name,
		"source_detail_name": source_detail_name or source_detail,
		"charge_key": f"{doc.doctype}:{doc.name}:{source_type}:{source_detail}",
		"item_code": item_code,
		"item_name": item.get("item_name") or item_code,
		"description": description or source_type,
		"qty": qty,
		"uom": resolved_uom,
		"rate": rate,
		"amount": amount,
		"income_account": _get_item_income_account(item_code, company),
		"cost_center": cost_center,
		"branch": branch,
		"notes": notes,
	}


def get_source_charge_company(doc) -> str | None:
	if doc.get("company"):
		return doc.get("company")
	try:
		return get_default_company()
	except Exception:
		return None


def _safe_nowdate():
	try:
		return nowdate()
	except Exception:
		return None


def _get_branch_price_list(branch):
	if not branch or not frappe.db.exists("DocType", "Branch"):
		return None
	for fieldname in ("vetedge_price_list", "selling_price_list"):
		if _doctype_has_field("Branch", fieldname):
			price_list = frappe.db.get_value("Branch", branch, fieldname)
			if price_list:
				return price_list
	return None


def _get_default_selling_price_list(company=None):
	if frappe.db.exists("DocType", "Veterinary Settings") and _doctype_has_field("Veterinary Settings", "default_selling_price_list"):
		price_list = frappe.db.get_single_value("Veterinary Settings", "default_selling_price_list")
		if price_list:
			return price_list
	if frappe.db.exists("DocType", "Selling Settings") and _doctype_has_field("Selling Settings", "selling_price_list"):
		price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list")
		if price_list:
			return price_list
	if frappe.db.exists("Price List", "Standard Selling"):
		return "Standard Selling"
	return None


def _resolve_selling_price_list(company=None, customer=None, branch=None, source_doc=None, explicit_price_list=None):
	if explicit_price_list:
		return explicit_price_list
	branch = branch or (source_doc.get("service_branch") or source_doc.get("branch") or source_doc.get("default_branch") if source_doc else None)
	price_list = _get_branch_price_list(branch)
	if price_list:
		return price_list
	return _get_default_selling_price_list(company=company)


def _get_item_selling_rate(item_code, company=None, customer=None, branch=None, price_list=None, posting_date=None, uom=None):
	if not item_code:
		return 0
	posting_date = posting_date or _safe_nowdate()
	price_list = _resolve_selling_price_list(company=company, customer=customer, branch=branch, explicit_price_list=price_list)
	if price_list and frappe.db.exists("DocType", "Item Price"):
		filters = {"item_code": item_code, "price_list": price_list}
		if _doctype_has_field("Item Price", "selling"):
			filters["selling"] = 1
		fields = ["name", "price_list_rate"]
		for fieldname in ("uom", "valid_from", "valid_upto"):
			if _doctype_has_field("Item Price", fieldname):
				fields.append(fieldname)
		order_by = "valid_from desc" if _doctype_has_field("Item Price", "valid_from") else "modified desc"
		rows = frappe.get_all("Item Price", filters=filters, fields=fields, order_by=order_by)
		valid_rows = []
		for row in rows:
			valid_from = row.get("valid_from")
			valid_upto = row.get("valid_upto")
			if valid_from and str(valid_from) > str(posting_date):
				continue
			if valid_upto and str(valid_upto) < str(posting_date):
				continue
			valid_rows.append(row)
		if uom and _doctype_has_field("Item Price", "uom"):
			exact = [row for row in valid_rows if row.get("uom") == uom]
			if exact:
				valid_rows = exact
		if valid_rows:
			return flt(valid_rows[0].get("price_list_rate"))
	item = frappe.db.get_value("Item", item_code, "standard_rate")
	return flt(item)


def _doctype_has_field(doctype, fieldname):
	try:
		meta = frappe.get_meta(doctype)
		return bool(meta.get_field(fieldname))
	except Exception:
		return False


def _get_item_income_account(item_code, company=None):
	if not item_code:
		return None

	if _doctype_has_field("Item Default", "income_account"):
		if company:
			income_account = frappe.db.get_value(
				"Item Default",
				{"parent": item_code, "company": company},
				"income_account",
			)
			if income_account:
				return income_account

		income_account = frappe.db.get_value(
			"Item Default",
			{"parent": item_code},
			"income_account",
		)
		if income_account:
			return income_account

	item_group = frappe.db.get_value("Item", item_code, "item_group")
	if item_group:
		for fieldname in ("income_account", "default_income_account"):
			if _doctype_has_field("Item Group", fieldname):
				income_account = frappe.db.get_value("Item Group", item_group, fieldname)
				if income_account:
					return income_account

	if company and _doctype_has_field("Company", "default_income_account"):
		income_account = frappe.db.get_value(
			"Company",
			company,
			"default_income_account",
		)
		if income_account:
			return income_account

	return None


def normalize_charge_payload(charge, charge_key, session):
	qty = flt(charge.get("qty")) or 1
	rate = flt(charge.get("rate"))
	amount = flt(charge.get("amount") if charge.get("amount") is not None else qty * rate)
	if not rate and amount and qty:
		rate = flt(amount / qty)
	if not amount and rate:
		amount = flt(qty * rate)
	return {
		"source_doctype": charge.get("source_doctype"),
		"source_name": charge.get("source_name"),
		"source_detail_name": charge.get("source_detail_name"),
		"charge_key": charge_key,
		"item_code": charge.get("item_code"),
		"item_name": charge.get("item_name") or charge.get("item_code"),
		"description": charge.get("description"),
		"qty": qty,
		"uom": charge.get("uom"),
		"rate": rate,
		"amount": amount,
		"income_account": charge.get("income_account"),
		"cost_center": charge.get("cost_center"),
		"branch": charge.get("branch") or session.get("branch"),
		"stock_affecting": cint(charge.get("stock_affecting")),
		"stock_status": charge.get("stock_status"),
		"notes": charge.get("notes"),
	}


def build_charge_key(charge) -> str:
	parts = [charge.get("source_doctype"), charge.get("source_name"), charge.get("source_detail_name"), charge.get("item_code")]
	return ":".join(str(part) for part in parts if part)


def get_session_charge(session, charge_key: str):
	return get_existing_charge_by_key(session, charge_key)


def get_existing_charge_by_key(session, charge_key: str):
	for row in session.get("charges") or []:
		if row.get("charge_key") == charge_key:
			return row
	return None


def is_charge_already_submitted(charge) -> bool:
	invoice_name = charge.get("invoice")
	if invoice_name and frappe.db.exists("Sales Invoice", invoice_name):
		return cint(frappe.db.get_value("Sales Invoice", invoice_name, "docstatus")) == 1
	return charge.get("billing_status") in {"Submitted Invoiced", "Paid"}


def is_source_detail_already_billed(session, charge_key: str) -> bool:
	charge = get_existing_charge_by_key(session, charge_key)
	return bool(charge and is_charge_already_submitted(charge))


def get_unbilled_source_payloads(session, source_doctype: str, source_name: str) -> list[dict]:
	session = ensure_session_doc(session)
	payloads = get_source_charge_payloads(source_doctype, source_name, session)
	return [payload for payload in payloads if not is_source_detail_already_billed(session, payload.get("charge_key") or build_charge_key(payload))]


def apply_invoice_session_defaults(invoice, session) -> None:
	invoice.customer = session.customer
	invoice.company = session.company or get_default_company()
	invoice.posting_date = nowdate()
	invoice.due_date = invoice.get("due_date") or invoice.posting_date
	if session.get("branch") and frappe.get_meta("Sales Invoice").has_field("branch"):
		invoice.branch = session.branch
	if session.get("branch") and frappe.get_meta("Sales Invoice").has_field("cost_center"):
		invoice.cost_center = get_billing_cost_center(session.branch, required=False)
	normalize_billing_session_invoice_dates(invoice)


def normalize_billing_session_invoice_dates(invoice) -> None:
	posting_date = invoice.get("posting_date") or nowdate()
	due_date = invoice.get("due_date") or posting_date
	if getdate(due_date) < getdate(posting_date):
		due_date = posting_date
	invoice.posting_date = posting_date
	invoice.due_date = due_date
	# Hospitalisation/session stock usage is posted explicitly with Stock Entry, not Sales Invoice stock update.
	if invoice.get("update_stock"):
		invoice.update_stock = 0


def append_invoice_item_from_charge(invoice, charge):
	row = build_invoice_item_from_charge(charge)
	return invoice.append("items", row)


def update_invoice_item_from_charge(row, charge) -> None:
	for fieldname, value in build_invoice_item_from_charge(charge).items():
		setattr(row, fieldname, value)


def build_invoice_item_from_charge(charge) -> dict:
	description = charge.get("description") or charge.get("item_name") or charge.get("item_code")
	qty, rate, amount = get_charge_invoice_values(charge)
	return {
		"item_code": charge.item_code,
		"item_name": charge.get("item_name"),
		"description": f"{description}\nVetEdge billing charge: {charge.charge_key}",
		"qty": qty,
		"uom": charge.get("uom"),
		"rate": rate,
		"amount": amount,
		"income_account": charge.get("income_account"),
		"cost_center": charge.get("cost_center"),
	}


def get_charge_invoice_values(charge) -> tuple[float, float, float]:
	qty = flt(charge.get("qty")) or 1
	rate = flt(charge.get("rate"))
	amount = flt(charge.get("amount") if charge.get("amount") is not None else qty * rate)
	if not rate and amount and qty:
		rate = flt(amount / qty)
	if not amount and rate:
		amount = flt(qty * rate)
	return qty, rate, amount


def _prepare_sales_invoice_totals(invoice):
	set_missing_values = getattr(invoice, "set_missing_values", None)
	if callable(set_missing_values):
		set_missing_values()
	calculate_taxes_and_totals = getattr(invoice, "calculate_taxes_and_totals", None)
	if callable(calculate_taxes_and_totals):
		calculate_taxes_and_totals()
	numeric_fields = (
		"total",
		"net_total",
		"base_total",
		"base_net_total",
		"grand_total",
		"base_grand_total",
		"rounded_total",
		"base_rounded_total",
		"outstanding_amount",
	)
	for fieldname in numeric_fields:
		if getattr(invoice, fieldname, None) is None:
			setattr(invoice, fieldname, 0)
	return invoice


def get_invoice_item_charge_index(invoice) -> dict[str, object]:
	index = {}
	for row in invoice.get("items") or []:
		key = extract_charge_key_from_invoice_item(row)
		if key:
			index[key] = row
	return index


def extract_charge_key_from_invoice_item(row) -> str | None:
	description = row.get("description") or ""
	marker = "VetEdge billing charge:"
	if marker in description:
		return description.split(marker, 1)[1].strip().splitlines()[0]
	return None


def reconcile_session_charge_statuses(session) -> None:
	for row in session.get("charges") or []:
		if row.get("billing_status") in {"Cancelled", "Skipped"}:
			continue
		if not row.get("invoice") or not frappe.db.exists("Sales Invoice", row.invoice):
			if row.get("billing_status") != "Skipped":
				row.billing_status = "Pending"
			continue
		docstatus = cint(frappe.db.get_value("Sales Invoice", row.invoice, "docstatus"))
		if docstatus == 0:
			row.billing_status = "Draft Invoiced"
		elif docstatus == 1:
			state = get_invoice_payment_state(row.invoice)
			row.billing_status = "Paid" if flt(state.get("outstanding_amount")) <= 0 else "Submitted Invoiced"
		elif docstatus == 2:
			row.billing_status = "Cancelled"


def get_session_invoice_names(session) -> list[str]:
	names = []
	for row in session.get("charges") or []:
		if row.get("invoice") and row.invoice not in names:
			names.append(row.invoice)
	for fieldname in ("current_draft_invoice", "latest_invoice"):
		if session.get(fieldname) and session.get(fieldname) not in names:
			names.append(session.get(fieldname))
	return names


def get_session_invoice_summaries(session) -> list[dict]:
	return get_billing_session_invoice_ledger(session)["invoices"]


def get_session_payment_status(session, invoice_names: Iterable[str]) -> str:
	return get_billing_session_invoice_ledger(session)["payment_status"]


def serialize_charge(row) -> dict:
	return {
		"charge_key": row.get("charge_key"),
		"source_doctype": row.get("source_doctype"),
		"source_name": row.get("source_name"),
		"item_code": row.get("item_code"),
		"item_name": row.get("item_name"),
		"qty": flt(row.get("qty")),
		"rate": flt(row.get("rate")),
		"amount": flt(row.get("amount")),
		"invoice": row.get("invoice"),
		"billing_status": row.get("billing_status"),
	}


def update_source_billing_compatibility_fields(source_doctype: str, source_name: str, summary: dict | None = None) -> None:
	summary = summary or {}
	invoice_name = summary.get("current_draft_invoice") or summary.get("latest_invoice")
	if not invoice_name:
		return

	field_map = {
		"Veterinary Consultation": "linked_invoice",
		"Veterinary Lab Order": "linked_invoice",
		"Veterinary Vaccination Record": "linked_invoice",
		"Veterinary Hospitalisation": "sales_invoice",
		"Pet Grooming Session": "linked_invoice",
		"Pet Boarding Booking": "linked_invoice",
		"Veterinary Patient": "registration_invoice",
	}
	fieldname = field_map.get(source_doctype)
	if not fieldname or not frappe.db.exists(source_doctype, source_name):
		return
	values = {fieldname: invoice_name}
	if source_doctype == "Veterinary Patient":
		values.update({"registration_billed": 1, "registration_status": get_registration_compatibility_status(summary)})
	elif source_doctype == "Veterinary Hospitalisation":
		values["invoice_status"] = get_select_safe_invoice_status(source_doctype, "invoice_status", summary.get("payment_status"))
	elif source_doctype in {"Veterinary Consultation"}:
		values["payment_status"] = summary.get("payment_status")
	frappe.db.set_value(source_doctype, source_name, values, update_modified=False)

	if source_doctype == "Pet Grooming Session":
		appointment = frappe.db.get_value(source_doctype, source_name, "appointment")
		if appointment:
			frappe.db.set_value("Pet Grooming Appointment", appointment, "linked_invoice", invoice_name, update_modified=False)


def update_all_session_source_compatibility_fields(summary: dict | None = None) -> None:
	if not summary:
		return
	for source in summary.get("source_documents") or []:
		update_source_billing_compatibility_fields(source.get("doctype"), source.get("name"), summary)


def get_select_safe_invoice_status(doctype: str, fieldname: str, status: str | None) -> str:
	status_map = {
		"Draft Invoice Pending": "Draft",
		"Pending Invoice": "Not Invoiced",
		"Partially Paid": "Partly Paid",
	}
	status = status_map.get(status or "Not Invoiced", status or "Not Invoiced")
	try:
		field = frappe.get_meta(doctype).get_field(fieldname)
		if field and field.fieldtype == "Select":
			options = {option.strip() for option in (field.options or "").split("\n") if option.strip()}
			if options and status not in options:
				return "Not Invoiced" if "Not Invoiced" in options else next(iter(options))
	except Exception:
		pass
	return status


def get_registration_compatibility_status(summary: dict) -> str:
	if summary.get("payment_status") == "Paid":
		return "Registration Paid"
	return "Awaiting Registration Payment"


def ensure_session_doc(session):
	if isinstance(session, str):
		return frappe.get_doc(BILLING_SESSION_DOCTYPE, session)
	return session
