from __future__ import annotations

import frappe
from frappe.utils import cint, flt

from vetedge.services.portal_access import require_internal_user
from vetedge.services.permissions import can_access_consultation


FINANCIAL_RESOLUTION_ACTIONS = [
	"retain_payment_clinical_cancel_only",
	"refund_required",
	"issue_customer_credit",
	"reschedule_consultation",
	"admin_accounting_correction",
]

RESOLUTION_ACTION_LABELS = {
	"cancel_consultation": "Cancel consultation",
	"admin_review_required": "Admin review required",
	"retain_payment_clinical_cancel_only": "Retain payment and cancel clinical record only",
	"refund_required": "Refund required",
	"issue_customer_credit": "Issue customer credit",
	"reschedule_consultation": "Reschedule consultation",
	"admin_accounting_correction": "Admin/accounting correction",
	"review_draft_dependencies_then_cancel": "Review draft dependencies, then cancel",
	"choose_financial_resolution": "Choose a financial resolution",
}

LAB_FINAL_STATUSES = {"Result Entered", "Awaiting Review", "Reviewed", "Completed"}
VACCINATION_FINAL_STATUSES = {"Administered"}
HOSPITALISATION_ACTIVE_STATUSES = {"Admitted", "Under Care", "Ready for Discharge"}


@frappe.whitelist()
def get_consultation_cancellation_preflight(consultation_name: str) -> dict:
	require_internal_user()
	can_access_consultation(frappe.session.user, consultation_name, raise_exception=True)
	return build_consultation_cancellation_preflight(consultation_name)


@frappe.whitelist()
def cancel_consultation_safely(consultation_name: str, reason: str | None = None) -> dict:
	require_internal_user()
	can_access_consultation(frappe.session.user, consultation_name, raise_exception=True)
	return execute_consultation_cancellation(consultation_name, reason=reason)


def execute_consultation_cancellation(consultation_name: str, reason: str | None = None) -> dict:
	preflight = validate_consultation_can_be_cancelled(consultation_name)
	cleanup_result = cleanup_safe_draft_dependencies(consultation_name, preflight)

	consultation = frappe.get_doc("Veterinary Consultation", consultation_name)
	consultation.status = "Cancelled"
	if reason:
		set_cancellation_reason_if_supported(consultation, reason)
	consultation.save()

	return {
		"status": consultation.status,
		"consultation": consultation.name,
		"cleaned_draft_invoices": cleanup_result["cleaned_draft_invoices"],
		"closed_billing_sessions": cleanup_result["closed_billing_sessions"],
		"warnings": preflight.get("warnings") or [],
		"preserved_references": cleanup_result["preserved_references"],
		"message": "Consultation cancelled after safe draft cleanup.",
	}


def build_consultation_cancellation_preflight(consultation_name: str) -> dict:
	consultation = frappe.get_doc("Veterinary Consultation", consultation_name)
	blockers: list[dict] = []
	warnings: list[dict] = []

	linked_invoices = get_consultation_billing_group_invoices(consultation_name)
	billing_group_summary = summarize_invoice_history(linked_invoices)
	add_invoice_blockers(blockers, warnings, linked_invoices, billing_group_summary)
	outstanding_context = get_consultation_patient_outstanding_context(consultation, linked_invoices)

	linked_lab_orders = get_linked_lab_orders(consultation_name)
	add_lab_order_blockers(blockers, warnings, linked_lab_orders)

	linked_vaccinations = get_linked_vaccinations(consultation_name)
	add_vaccination_blockers(blockers, warnings, linked_vaccinations)

	linked_planned_treatments = get_linked_planned_treatments(consultation)
	add_planned_treatment_warnings(warnings, linked_planned_treatments)

	linked_hospitalisations = get_linked_hospitalisations(consultation_name)
	add_hospitalisation_blockers(blockers, warnings, linked_hospitalisations)

	linked_stock_entries = get_linked_stock_entries(consultation_name)
	add_stock_entry_blockers(blockers, warnings, linked_stock_entries)

	linked_billing_sessions = get_linked_billing_sessions(consultation_name)
	linked_notifications = get_linked_notifications(consultation_name)

	can_cancel = not blockers
	allowed_actions = get_allowed_cancellation_actions(billing_group_summary, can_cancel)
	return {
		"can_cancel": can_cancel,
		"consultation": consultation.name,
		"current_status": consultation.get("status"),
		"billing_group_summary": billing_group_summary,
		"linked_invoices": linked_invoices,
		"outstanding_context": outstanding_context,
		"linked_lab_orders": linked_lab_orders,
		"linked_vaccinations": linked_vaccinations,
		"linked_planned_treatments": linked_planned_treatments,
		"linked_hospitalisations": linked_hospitalisations,
		"linked_stock_entries": linked_stock_entries,
		"linked_billing_sessions": linked_billing_sessions,
		"linked_notifications": linked_notifications,
		"blockers": blockers,
		"warnings": warnings,
		"allowed_actions": allowed_actions,
		"allowed_action_options": get_cancellation_action_options(allowed_actions),
		"recommended_next_action": get_recommended_cancellation_action(blockers, warnings, billing_group_summary),
	}


def validate_consultation_can_be_cancelled(consultation_name: str) -> dict:
	preflight = build_consultation_cancellation_preflight(consultation_name)
	if preflight["can_cancel"]:
		return preflight

	message = build_cancellation_blocker_message(preflight)
	frappe.throw(message, frappe.ValidationError)
	return preflight


def cleanup_safe_draft_dependencies(consultation_name: str, preflight: dict) -> dict:
	cleaned_draft_invoices: list[str] = []
	preserved_references: list[dict] = []
	for row in preflight.get("linked_invoices") or []:
		if cint(row.get("docstatus")) != 0:
			preserved_references.append({"invoice": row.get("invoice"), "reason": "non_draft_invoice_preserved"})
			continue
		invoice_name = row.get("invoice") or row.get("name")
		if not invoice_name:
			continue
		if not is_draft_invoice_safe_for_consultation_cleanup(invoice_name, consultation_name):
			frappe.throw(
				f"Draft invoice {invoice_name} is not exclusive to this consultation billing group and was not cleaned up.",
				frappe.ValidationError,
			)
		cleanup_draft_invoice_for_consultation(invoice_name, consultation_name)
		cleaned_draft_invoices.append(invoice_name)

	closed_billing_sessions = close_safe_draft_billing_sessions(consultation_name)
	return {
		"cleaned_draft_invoices": cleaned_draft_invoices,
		"closed_billing_sessions": closed_billing_sessions,
		"preserved_references": preserved_references,
	}


def is_draft_invoice_safe_for_consultation_cleanup(invoice_name: str, consultation_name: str) -> bool:
	if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
		return False
	if cint(frappe.db.get_value("Sales Invoice", invoice_name, "docstatus")) != 0:
		return False
	if not safe_doctype_exists("Veterinary Billing Session Charge"):
		return True
	rows = frappe.get_all(
		"Veterinary Billing Session Charge",
		filters={"invoice": invoice_name},
		fields=["source_doctype", "source_name"],
		limit=100,
	)
	for row in rows:
		if not source_belongs_to_consultation_group(row.get("source_doctype"), row.get("source_name"), consultation_name):
			return False
	return True


def source_belongs_to_consultation_group(source_doctype: str | None, source_name: str | None, consultation_name: str) -> bool:
	if not source_doctype or not source_name:
		return True
	if source_doctype == "Veterinary Consultation":
		return source_name == consultation_name
	field_map = {
		"Veterinary Lab Order": "consultation",
		"Veterinary Vaccination Record": "linked_consultation",
		"Veterinary Hospitalisation": "linked_consultation",
	}
	fieldname = field_map.get(source_doctype)
	if fieldname and safe_doctype_exists(source_doctype) and frappe.get_meta(source_doctype).has_field(fieldname):
		return frappe.db.get_value(source_doctype, source_name, fieldname) == consultation_name
	return False


def cleanup_draft_invoice_for_consultation(invoice_name: str, consultation_name: str) -> None:
	from vetedge.services.billing_core import (
		detach_invoice_from_billing_session,
		detach_invoice_from_vetedge_sources,
		run_with_billing_core_sync_flag,
	)

	session_names = get_billing_session_names_for_invoice(invoice_name, consultation_name)
	for session_name in session_names:
		session = frappe.get_doc("Veterinary Billing Session", session_name)
		session = detach_invoice_from_billing_session(session, invoice_name, reason="consultation_cancelled")
		for charge in session.get("charges") or []:
			if charge.get("billing_status") not in {"Submitted Invoiced", "Paid", "Cancelled", "Skipped"}:
				charge.billing_status = "Cancelled"
		session.save()
	detach_invoice_from_vetedge_sources(invoice_name, reason="consultation_cancelled")
	run_with_billing_core_sync_flag(lambda: frappe.delete_doc("Sales Invoice", invoice_name))


def get_billing_session_names_for_invoice(invoice_name: str, consultation_name: str | None = None) -> list[str]:
	if not safe_doctype_exists("Veterinary Billing Session Charge"):
		return []
	session_names = []
	for row in frappe.get_all("Veterinary Billing Session Charge", filters={"invoice": invoice_name}, fields=["parent"], limit=100):
		if row.get("parent") and row.get("parent") not in session_names:
			session_names.append(row.get("parent"))
	if session_names or not consultation_name:
		return session_names
	return [
		row.get("name")
		for row in get_linked_billing_sessions(consultation_name)
		if row.get("current_draft_invoice") == invoice_name or row.get("latest_invoice") == invoice_name
	]


def close_safe_draft_billing_sessions(consultation_name: str) -> list[str]:
	closed: list[str] = []
	for row in get_linked_billing_sessions(consultation_name):
		session_name = row.get("name")
		if not session_name or not frappe.db.exists("Veterinary Billing Session", session_name):
			continue
		session = frappe.get_doc("Veterinary Billing Session", session_name)
		if not is_billing_session_safe_to_cancel_for_consultation(session, consultation_name):
			continue
		session.status = "Cancelled"
		if session.get("current_draft_invoice"):
			session.current_draft_invoice = None
		if session.get("latest_invoice") and not frappe.db.exists("Sales Invoice", session.get("latest_invoice")):
			session.latest_invoice = None
		for charge in session.get("charges") or []:
			if charge.get("billing_status") not in {"Submitted Invoiced", "Paid", "Cancelled", "Skipped"}:
				charge.billing_status = "Cancelled"
		session.save()
		closed.append(session.name)
	return closed


def is_billing_session_safe_to_cancel_for_consultation(session, consultation_name: str) -> bool:
	if session.get("status") in {"Closed", "Cancelled", "Paid"}:
		return False
	for invoice_name in filter(None, {session.get("current_draft_invoice"), session.get("latest_invoice")}):
		if frappe.db.exists("Sales Invoice", invoice_name) and cint(frappe.db.get_value("Sales Invoice", invoice_name, "docstatus")) != 0:
			return False
	for charge in session.get("charges") or []:
		if charge.get("billing_status") in {"Submitted Invoiced", "Paid"}:
			return False
		if not source_belongs_to_consultation_group(charge.get("source_doctype"), charge.get("source_name"), consultation_name):
			return False
	return True


def set_cancellation_reason_if_supported(consultation, reason: str) -> None:
	meta = frappe.get_meta("Veterinary Consultation")
	for fieldname in ("cancellation_reason", "cancel_reason", "reason_for_cancellation"):
		if meta.has_field(fieldname):
			consultation.set(fieldname, reason)
			return


def build_cancellation_blocker_message(preflight: dict) -> str:
	lines = ["This consultation cannot be cancelled directly."]
	blockers = preflight.get("blockers") or []
	if any(blocker.get("type") in {"submitted_invoice", "paid_invoice"} for blocker in blockers):
		lines.append("Submitted invoices cannot be changed automatically.")
	if flt((preflight.get("billing_group_summary") or {}).get("paid_amount")) > 0:
		lines.append("This consultation has paid or partly paid invoices. Choose a financial resolution before cancellation.")
	for blocker in blockers[:5]:
		message = blocker.get("message")
		if message and message not in lines:
			lines.append(message)
	lines.append("Use refund, credit, reschedule, or admin correction depending on clinic policy.")
	return "\n".join(lines)


def get_consultation_billing_group_invoices(consultation_name: str) -> list[dict]:
	from vetedge.services.billing_core import get_billing_group_invoice_history

	rows = []
	for row in get_billing_group_invoice_history("Veterinary Consultation", consultation_name, include_related=True):
		invoice_name = row.get("name") or row.get("invoice")
		if not invoice_name:
			continue
		rows.append(
			{
				"invoice": invoice_name,
				"name": invoice_name,
				"docstatus": cint(row.get("docstatus")),
				"status": row.get("status"),
				"payment_state": row.get("payment_state") or row.get("payment_status") or row.get("status"),
				"grand_total": flt(row.get("grand_total")),
				"paid_amount": flt(row.get("paid_amount")),
				"outstanding_amount": flt(row.get("outstanding_amount")),
				"billing_session": row.get("billing_session"),
				"relation_type": row.get("relation_type"),
				"source_doctype": row.get("source_doctype"),
				"source_name": row.get("source_name"),
				"is_active_session_invoice": bool(row.get("is_active_session_invoice")),
				"is_history_invoice": bool(row.get("is_history_invoice")),
			}
		)
	return rows


def get_consultation_patient_outstanding_context(consultation, linked_invoices: list[dict] | None = None) -> list[dict]:
	from vetedge.services.billing_core import get_patient_outstanding_invoice_context

	excluded = {row.get("name") or row.get("invoice") for row in linked_invoices or []}
	return get_patient_outstanding_invoice_context(
		patient=consultation.get("patient"),
		customer=consultation.get("primary_owner") or consultation.get("customer"),
		exclude_billing_group=excluded,
	)


def summarize_invoice_history(invoice_history: list[dict]) -> dict:
	active_rows = [row for row in invoice_history if cint(row.get("docstatus")) != 2]
	submitted_rows = [row for row in active_rows if cint(row.get("docstatus")) == 1]
	draft_rows = [row for row in active_rows if cint(row.get("docstatus")) == 0]
	paid_amount = sum(flt(row.get("paid_amount")) for row in submitted_rows)
	outstanding_amount = sum(flt(row.get("outstanding_amount")) for row in submitted_rows)
	total_amount = sum(flt(row.get("grand_total")) for row in active_rows)
	return {
		"linked_invoice_count": len(active_rows),
		"submitted_invoice_count": len(submitted_rows),
		"draft_invoice_count": len(draft_rows),
		"cancelled_invoice_count": len(invoice_history) - len(active_rows),
		"total_amount": total_amount,
		"paid_amount": paid_amount,
		"outstanding_amount": outstanding_amount,
		"payment_status": get_group_payment_status(paid_amount, outstanding_amount, submitted_rows),
	}


def get_group_payment_status(paid_amount: float, outstanding_amount: float, submitted_rows: list[dict]) -> str:
	if not submitted_rows:
		return "Not Billed"
	if paid_amount <= 0:
		return "Unpaid"
	if outstanding_amount <= 0:
		return "Paid"
	return "Partly Paid"


def add_invoice_blockers(blockers: list[dict], warnings: list[dict], invoices: list[dict], summary: dict) -> None:
	for row in invoices:
		docstatus = cint(row.get("docstatus"))
		if docstatus == 0:
			warnings.append(
				{
					"type": "draft_invoice",
					"invoice": row.get("invoice"),
					"message": f"Draft invoice {row.get('invoice')} is linked and should be cleaned up through Billing Core if cancellation proceeds.",
				}
			)
			continue
		if docstatus != 1:
			continue
		if flt(row.get("paid_amount")) > 0:
			blockers.append(
				{
					"type": "paid_invoice",
					"invoice": row.get("invoice"),
					"message": f"Invoice {row.get('invoice')} has payment recorded and needs a financial resolution before cancellation.",
				}
			)
		else:
			blockers.append(
				{
					"type": "submitted_invoice",
					"invoice": row.get("invoice"),
					"message": f"Submitted invoice {row.get('invoice')} exists and must be handled by accounts/admin before cancellation.",
				}
			)

	if flt(summary.get("paid_amount")) > 0 and not any(blocker.get("type") == "paid_invoice" for blocker in blockers):
		blockers.append(
			{
				"type": "paid_invoice",
				"message": "The billing group has paid amount recorded and needs a financial resolution before cancellation.",
			}
		)


def get_linked_lab_orders(consultation_name: str) -> list[dict]:
	return get_linked_docs(
		"Veterinary Lab Order",
		{"consultation": consultation_name},
		["name", "status", "docstatus", "linked_invoice"],
	)


def add_lab_order_blockers(blockers: list[dict], warnings: list[dict], rows: list[dict]) -> None:
	for row in rows:
		if row.get("status") in {"Cancelled"} or cint(row.get("docstatus")) == 2:
			continue
		target = blockers if row.get("status") in LAB_FINAL_STATUSES or cint(row.get("docstatus")) == 1 else warnings
		target.append(
			{
				"type": "linked_lab_order",
				"document": row.get("name"),
				"status": row.get("status"),
				"message": f"Linked lab order {row.get('name')} is {row.get('status') or 'active'} and must be resolved before cancellation.",
			}
		)


def get_linked_vaccinations(consultation_name: str) -> list[dict]:
	return get_linked_docs(
		"Veterinary Vaccination Record",
		{"linked_consultation": consultation_name},
		["name", "status", "docstatus", "linked_invoice", "sales_invoice", "stock_entry"],
	)


def add_vaccination_blockers(blockers: list[dict], warnings: list[dict], rows: list[dict]) -> None:
	for row in rows:
		if row.get("status") in {"Cancelled"} or cint(row.get("docstatus")) == 2:
			continue
		target = blockers if row.get("status") in VACCINATION_FINAL_STATUSES or cint(row.get("docstatus")) == 1 else warnings
		target.append(
			{
				"type": "linked_vaccination",
				"document": row.get("name"),
				"status": row.get("status"),
				"message": f"Linked vaccination {row.get('name')} is {row.get('status') or 'active'} and must be resolved before cancellation.",
			}
		)


def get_linked_planned_treatments(consultation) -> list[dict]:
	rows = []
	for row in consultation.get("planned_treatments") or []:
		rows.append(
			{
				"name": row.get("name"),
				"item": row.get("item") or row.get("item_code"),
				"description": row.get("description"),
				"billing_status": row.get("billing_status"),
				"payment_status": row.get("payment_status"),
				"source_type": row.get("source_type"),
				"source_doctype": row.get("source_doctype"),
				"source_document": row.get("source_document"),
				"source_detail_name": row.get("source_detail_name"),
			}
		)
	return rows


def add_planned_treatment_warnings(warnings: list[dict], rows: list[dict]) -> None:
	for row in rows:
		source_type = row.get("source_type")
		source_document = row.get("source_document")
		if not source_type and not source_document:
			continue
		warnings.append(
			{
				"type": "source_linked_planned_treatment",
				"document": row.get("name"),
				"source_type": source_type,
				"source_document": source_document,
				"message": (
					f"Planned treatment row {row.get('name') or row.get('item') or ''} is linked to "
					f"{source_type or 'a source document'} {source_document or ''} and will not be silently removed."
				).strip(),
			}
		)


def get_linked_hospitalisations(consultation_name: str) -> list[dict]:
	return get_linked_docs(
		"Veterinary Hospitalisation",
		{"linked_consultation": consultation_name},
		["name", "status", "docstatus", "sales_invoice"],
	)


def add_hospitalisation_blockers(blockers: list[dict], warnings: list[dict], rows: list[dict]) -> None:
	for row in rows:
		if row.get("status") in {"Cancelled", "Discharged"} or cint(row.get("docstatus")) == 2:
			continue
		target = blockers if row.get("status") in HOSPITALISATION_ACTIVE_STATUSES or cint(row.get("docstatus")) == 1 else warnings
		target.append(
			{
				"type": "linked_hospitalisation",
				"document": row.get("name"),
				"status": row.get("status"),
				"message": f"Linked hospitalisation {row.get('name')} is {row.get('status') or 'active'} and must be resolved before cancellation.",
			}
		)


def get_linked_stock_entries(consultation_name: str) -> list[dict]:
	if not safe_doctype_exists("Stock Entry"):
		return []
	fields = ["name", "docstatus", "stock_entry_type", "purpose"]
	meta = frappe.get_meta("Stock Entry")
	if meta.has_field("vetedge_consultation"):
		return get_linked_docs("Stock Entry", {"vetedge_consultation": consultation_name}, fields)
	if meta.has_field("consultation"):
		return get_linked_docs("Stock Entry", {"consultation": consultation_name}, fields)
	return []


def add_stock_entry_blockers(blockers: list[dict], warnings: list[dict], rows: list[dict]) -> None:
	for row in rows:
		if cint(row.get("docstatus")) == 2:
			continue
		target = blockers if cint(row.get("docstatus")) == 1 else warnings
		target.append(
			{
				"type": "linked_stock_entry",
				"document": row.get("name"),
				"docstatus": cint(row.get("docstatus")),
				"message": f"Linked Stock Entry {row.get('name')} must be handled by stock/accounts before cancellation.",
			}
		)


def get_linked_billing_sessions(consultation_name: str) -> list[dict]:
	rows: list[dict] = []
	if not safe_doctype_exists("Veterinary Billing Session"):
		return rows
	for filters in (
		{"source_context_doctype": "Veterinary Consultation", "source_context_name": consultation_name},
		{"created_from_doctype": "Veterinary Consultation", "created_from_name": consultation_name},
	):
		for row in get_linked_docs(
			"Veterinary Billing Session",
			filters,
			["name", "status", "payment_status", "current_draft_invoice", "latest_invoice", "total_paid", "outstanding_amount"],
		):
			if row.get("name") not in {existing.get("name") for existing in rows}:
				rows.append(row)
	return rows


def get_linked_notifications(consultation_name: str) -> list[dict]:
	for doctype in ("Veterinary Notification Item", "VetEdge Notification Item"):
		if not safe_doctype_exists(doctype):
			continue
		meta = frappe.get_meta(doctype)
		filters = {}
		if meta.has_field("reference_doctype") and meta.has_field("reference_name"):
			filters = {"reference_doctype": "Veterinary Consultation", "reference_name": consultation_name}
		elif meta.has_field("consultation"):
			filters = {"consultation": consultation_name}
		if filters:
			return get_linked_docs(doctype, filters, ["name", "status", "docstatus"])
	return []


def get_linked_docs(doctype: str, filters: dict, preferred_fields: list[str]) -> list[dict]:
	if not safe_doctype_exists(doctype):
		return []
	meta = frappe.get_meta(doctype)
	fields = [field for field in preferred_fields if field == "name" or meta.has_field(field)]
	if "name" not in fields:
		fields.insert(0, "name")
	try:
		return [frappe._dict(row) for row in frappe.get_all(doctype, filters=filters, fields=fields, order_by="modified desc")]
	except Exception:
		return []


def get_allowed_cancellation_actions(summary: dict, can_cancel: bool) -> list[str]:
	if can_cancel:
		return ["cancel_consultation"]
	if flt(summary.get("paid_amount")) > 0:
		return FINANCIAL_RESOLUTION_ACTIONS[:]
	return ["admin_review_required"]


def get_cancellation_action_options(actions: list[str]) -> list[dict]:
	return [
		{"value": action, "label": RESOLUTION_ACTION_LABELS.get(action, action.replace("_", " ").title())}
		for action in actions
	]


def get_recommended_cancellation_action(blockers: list[dict], warnings: list[dict], summary: dict) -> str:
	if not blockers:
		if warnings:
			return "review_draft_dependencies_then_cancel"
		return "cancel_consultation"
	if flt(summary.get("paid_amount")) > 0:
		return "choose_financial_resolution"
	return "admin_review_required"


def safe_doctype_exists(doctype: str) -> bool:
	try:
		return bool(frappe.db.exists("DocType", doctype))
	except Exception:
		return False
