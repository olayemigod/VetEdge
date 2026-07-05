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
