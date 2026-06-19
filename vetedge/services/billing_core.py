from __future__ import annotations

import json
from collections import OrderedDict
from typing import Iterable

import frappe
from frappe.utils import cint, flt, nowdate

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


def is_billing_sessions_enabled() -> bool:
	if not frappe.db.exists("DocType", BILLING_SESSION_DOCTYPE):
		return False
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return True
	meta = frappe.get_meta("Veterinary Settings")
	if not meta.has_field("enable_billing_sessions"):
		return True
	return bool(cint(frappe.get_single("Veterinary Settings").get("enable_billing_sessions")))


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
	rows = frappe.get_all(
		BILLING_SESSION_CHARGE_DOCTYPE,
		filters={"source_doctype": source_doctype, "source_name": source_name},
		fields=["parent"],
		order_by="modified desc",
		limit=1,
	)
	if rows:
		return frappe.get_doc(BILLING_SESSION_DOCTYPE, rows[0].parent)

	context = get_source_context(source_doctype, source_name)
	if context != (source_doctype, source_name):
		rows = frappe.get_all(
			BILLING_SESSION_DOCTYPE,
			filters={"source_context_doctype": context[0], "source_context_name": context[1], "status": ["!=", "Cancelled"]},
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
	customer = customer or source_doc.get("primary_owner") or source_doc.get("customer")
	animal = animal or source_doc.get("patient") or source_doc.get("animal")
	branch = branch or source_doc.get("service_branch") or source_doc.get("branch")
	company = company or source_doc.get("company") or get_default_company()
	if not customer:
		frappe.throw("Customer is required before creating a Billing Session.", frappe.ValidationError)

	context_doctype, context_name = get_source_context(source_doctype, source_name)
	session = frappe.get_doc(
		{
			"doctype": BILLING_SESSION_DOCTYPE,
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
	charge = frappe._dict(charge_payload or {})
	charge_key = charge.get("charge_key") or build_charge_key(charge)
	if not charge_key:
		frappe.throw("Billing Session charge_key is required.", frappe.ValidationError)

	existing = get_session_charge(session, charge_key)
	values = normalize_charge_payload(charge, charge_key, session)
	if existing:
		if existing.get("billing_status") in FINAL_INVOICE_STATUSES:
			return existing
		for fieldname, value in values.items():
			setattr(existing, fieldname, value)
		existing.billing_status = existing.get("billing_status") or "Pending"
		return existing

	row = session.append("charges", values)
	row.billing_status = row.get("billing_status") or "Pending"
	return row


def sync_session_charges_to_invoice(session):
	session = ensure_session_doc(session)
	reconcile_session_charge_statuses(session)
	pending = [row for row in session.get("charges") or [] if row.get("billing_status") in PENDING_STATUSES]
	if not pending:
		refresh_billing_session_totals(session)
		session.save()
		return {"session": session.name, "invoice": session.get("current_draft_invoice"), "added_count": 0, "updated_count": 0}

	invoice, created = create_or_update_draft_invoice_for_session(session)
	item_index = get_invoice_item_charge_index(invoice)
	added = updated = 0
	for charge in pending:
		key = charge.get("charge_key")
		if key in item_index:
			update_invoice_item_from_charge(item_index[key], charge)
			updated += 1
		else:
			item_index[key] = append_invoice_item_from_charge(invoice, charge)
			added += 1
		charge.invoice = invoice.name
		charge.invoice_item_name = item_index[key].get("name")
		charge.billing_status = "Draft Invoiced"

	invoice.save()
	session.current_draft_invoice = invoice.name
	session.latest_invoice = invoice.name
	refresh_billing_session_totals(session)
	session.save()
	return {"session": session.name, "invoice": invoice.name, "created": created, "added_count": added, "updated_count": updated}


def create_or_update_draft_invoice_for_session(session):
	session = ensure_session_doc(session)
	invoice_name = session.get("current_draft_invoice")
	if invoice_name and frappe.db.exists("Sales Invoice", invoice_name):
		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		if cint(invoice.docstatus) == 0:
			apply_invoice_session_defaults(invoice, session)
			return invoice, False
		session.current_draft_invoice = None

	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": session.customer,
			"company": session.company or get_default_company(),
			"posting_date": nowdate(),
			"due_date": nowdate(),
			"items": [],
			"remarks": f"VetEdge billing session {session.name}",
		}
	)
	apply_invoice_session_defaults(invoice, session)
	invoice.insert()
	session.current_draft_invoice = invoice.name
	session.latest_invoice = invoice.name
	return invoice, True


def get_billing_session_summary(session) -> dict:
	session = ensure_session_doc(session)
	refresh_billing_session_totals(session)
	invoices = get_session_invoice_summaries(session)
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
		"payment_gate": gate,
		"source_documents": [{"doctype": item.split(":", 1)[0], "name": item.split(":", 1)[1]} for item in source_documents],
		"charges": [serialize_charge(row) for row in session.get("charges") or []],
	}


def get_payment_gate_status(session) -> dict:
	session = ensure_session_doc(session)
	refresh_billing_session_totals(session)
	mode = normalize_payment_gate_mode(session.get("payment_gate_mode"))
	invoices = get_session_invoice_summaries(session)
	has_invoice = bool(invoices)
	has_submitted_invoice = any(cint(row.get("docstatus")) == 1 for row in invoices)

	if not has_invoice:
		return {"gate": mode, "can_proceed": False, "status": "Blocked", "message": "A Sales Invoice must be generated before service can proceed."}
	if mode == NO_PAYMENT_GATE:
		return {"gate": mode, "can_proceed": True, "status": "Allowed", "message": "Invoice has been generated. Payment is not required before proceeding."}
	if not has_submitted_invoice:
		return {"gate": mode, "can_proceed": False, "status": "Blocked", "message": "At least one linked Sales Invoice must be submitted before service can proceed."}
	if mode == PARTIAL_PAYMENT_GATE:
		allowed = flt(session.total_paid) > 0
		return {"gate": mode, "can_proceed": allowed, "status": "Allowed" if allowed else "Blocked", "message": "Payment gate passed." if allowed else "A partial payment is required before service can proceed."}
	allowed = flt(session.outstanding_amount) <= 0
	return {"gate": mode, "can_proceed": allowed, "status": "Allowed" if allowed else "Blocked", "message": "Payment gate passed." if allowed else "Full payment is required before service can proceed."}


def can_proceed_with_payment_gate(session) -> bool:
	return bool(get_payment_gate_status(session).get("can_proceed"))


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


def sync_source_to_billing_session(source_doctype: str, source_name: str):
	session = get_or_create_billing_session(source_doctype, source_name, payment_gate_mode=get_source_payment_gate_mode(source_doctype))
	for payload in get_source_charge_payloads(source_doctype, source_name, session):
		add_or_update_session_charge(session, payload)
	session.save()
	return sync_session_charges_to_invoice(session)


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
	return []


def refresh_billing_session_totals(session):
	session = ensure_session_doc(session)
	invoices = get_session_invoice_names(session)
	total_charges = sum(flt(row.amount) for row in session.get("charges") or [] if row.get("billing_status") != "Cancelled")
	total_invoiced = total_paid = outstanding = 0
	has_submitted_invoice = False
	has_draft_invoice = False
	for invoice_name in invoices:
		if not frappe.db.exists("Sales Invoice", invoice_name):
			continue
		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		if cint(invoice.docstatus) == 2:
			continue
		if cint(invoice.docstatus) == 0:
			has_draft_invoice = True
		total_invoiced += flt(invoice.get("grand_total"))
		if cint(invoice.docstatus) == 1:
			has_submitted_invoice = True
			state = get_invoice_payment_state(invoice.name)
			total_paid += flt(state.get("paid_amount"))
			outstanding += flt(state.get("outstanding_amount"))
	session.total_charges = total_charges
	session.total_invoiced = total_invoiced
	session.total_paid = total_paid
	session.outstanding_amount = outstanding
	session.payment_status = get_session_payment_status(session, invoices)
	session.billing_summary_json = json.dumps(
		{
			"invoice_count": len(invoices),
			"total_charges": total_charges,
			"total_invoiced": total_invoiced,
			"total_paid": total_paid,
			"outstanding_amount": outstanding,
		},
		default=str,
	)
	if session.status not in {"Closed", "Cancelled"}:
		if has_submitted_invoice and not has_draft_invoice and outstanding <= 0:
			session.status = "Paid"
		elif total_paid > 0:
			session.status = "Partially Paid"
		else:
			session.status = "Active"
	return session


def update_billing_sessions_from_invoice(doc, method: str | None = None) -> None:
	if not is_billing_sessions_enabled():
		return
	for session_name in get_sessions_for_invoice(doc.name):
		session = frappe.get_doc(BILLING_SESSION_DOCTYPE, session_name)
		reconcile_session_charge_statuses(session)
		refresh_billing_session_totals(session)
		session.save()


def update_billing_sessions_from_payment_entry(doc, method: str | None = None) -> None:
	if not is_billing_sessions_enabled():
		return
	invoice_names = [
		row.reference_name
		for row in doc.get("references") or []
		if row.reference_doctype == "Sales Invoice" and row.reference_name
	]
	for invoice_name in invoice_names:
		for session_name in get_sessions_for_invoice(invoice_name):
			session = frappe.get_doc(BILLING_SESSION_DOCTYPE, session_name)
			refresh_billing_session_totals(session)
			session.save()


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
	if settings.enable_treatment_billing:
		for row in doc.get("planned_treatments") or []:
			if row.get("item"):
				payloads.append(build_source_charge(doc, "Treatment", row.get("name") or f"{row.item}:{row.get('idx') or 0}", row.item, row.get("qty"), row.get("uom"), row.get("rate"), cost_center, row.get("description")))
	payloads.extend(get_lab_order_charge_payloads_for_consultation(doc.name, cost_center))
	payloads.extend(get_vaccination_charge_payloads_for_consultation(doc.name, cost_center))
	return payloads


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
	return [build_source_charge(patient, "Registration", patient.name, settings.default_registration_item, 1, None, settings.get("default_registration_fee"), cost_center)]


def build_source_charge(doc, source_type, source_detail, item_code, qty, uom, rate, cost_center, description=None, source_detail_name=None, notes=None):
	item = frappe.db.get_value("Item", item_code, ["item_name", "stock_uom", "standard_rate", "income_account"], as_dict=True) or {}
	qty = flt(qty) or 1
	rate = flt(rate) if rate not in (None, "") else flt(item.get("standard_rate"))
	return {
		"source_doctype": doc.doctype,
		"source_name": doc.name,
		"source_detail_name": source_detail_name or source_detail,
		"charge_key": f"{doc.doctype}:{doc.name}:{source_type}:{source_detail}",
		"item_code": item_code,
		"item_name": item.get("item_name") or item_code,
		"description": description or source_type,
		"qty": qty,
		"uom": uom or item.get("stock_uom"),
		"rate": rate,
		"amount": qty * rate,
		"income_account": item.get("income_account"),
		"cost_center": cost_center,
		"branch": doc.get("service_branch") or doc.get("branch") or doc.get("default_branch"),
		"notes": notes,
	}


def normalize_charge_payload(charge, charge_key, session):
	qty = flt(charge.get("qty")) or 1
	rate = flt(charge.get("rate"))
	amount = flt(charge.get("amount")) or qty * rate
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
	for row in session.get("charges") or []:
		if row.get("charge_key") == charge_key:
			return row
	return None


def apply_invoice_session_defaults(invoice, session) -> None:
	invoice.customer = session.customer
	invoice.company = session.company or get_default_company()
	invoice.posting_date = nowdate()
	invoice.due_date = nowdate()
	if session.get("branch") and frappe.get_meta("Sales Invoice").has_field("branch"):
		invoice.branch = session.branch
	if session.get("branch") and frappe.get_meta("Sales Invoice").has_field("cost_center"):
		invoice.cost_center = get_billing_cost_center(session.branch, required=False)


def append_invoice_item_from_charge(invoice, charge):
	row = build_invoice_item_from_charge(charge)
	return invoice.append("items", row)


def update_invoice_item_from_charge(row, charge) -> None:
	for fieldname, value in build_invoice_item_from_charge(charge).items():
		setattr(row, fieldname, value)


def build_invoice_item_from_charge(charge) -> dict:
	description = charge.get("description") or charge.get("item_name") or charge.get("item_code")
	return {
		"item_code": charge.item_code,
		"item_name": charge.get("item_name"),
		"description": f"{description}\nVetEdge billing charge: {charge.charge_key}",
		"qty": flt(charge.qty) or 1,
		"uom": charge.get("uom"),
		"rate": flt(charge.rate),
		"amount": flt(charge.amount),
		"income_account": charge.get("income_account"),
		"cost_center": charge.get("cost_center"),
	}


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
	summaries = []
	for invoice_name in get_session_invoice_names(session):
		if not frappe.db.exists("Sales Invoice", invoice_name):
			continue
		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		summaries.append(
			{
				"name": invoice.name,
				"docstatus": cint(invoice.docstatus),
				"status": invoice.get("status"),
				"grand_total": flt(invoice.get("grand_total")),
				"paid_amount": flt(invoice.get("paid_amount")),
				"outstanding_amount": flt(invoice.get("outstanding_amount")),
				"currency": invoice.get("currency"),
			}
		)
	return summaries


def get_session_payment_status(session, invoice_names: Iterable[str]) -> str:
	submitted = []
	draft_exists = False
	for invoice_name in invoice_names:
		if not frappe.db.exists("Sales Invoice", invoice_name):
			continue
		docstatus = cint(frappe.db.get_value("Sales Invoice", invoice_name, "docstatus"))
		if docstatus == 0:
			draft_exists = True
		elif docstatus == 1:
			submitted.append(invoice_name)
	if submitted and flt(session.outstanding_amount) <= 0:
		return "Paid"
	if flt(session.total_paid) > 0:
		return "Partly Paid"
	if draft_exists or submitted:
		return "Unpaid"
	return "Not Invoiced"


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


def ensure_session_doc(session):
	if isinstance(session, str):
		return frappe.get_doc(BILLING_SESSION_DOCTYPE, session)
	return session
