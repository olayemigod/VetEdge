from __future__ import annotations

import json

import frappe
from frappe.utils import cint, flt, now_datetime

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
CANCELLATION_RESOLUTION_DOCTYPE = "Veterinary Consultation Cancellation Resolution"
RESOLUTION_RECORDER_ROLES = {
	"System Manager",
	"VetEdge Administrator",
	"Branch Manager",
	"VetEdge Branch Manager",
	"Accounts/Cashier",
	"VetEdge Accounts/Cashier",
	"Accounts User",
	"Accounts Manager",
}
RETAIN_PAYMENT_EXECUTOR_ROLES = RESOLUTION_RECORDER_ROLES
RESCHEDULE_EXECUTOR_ROLES = RESOLUTION_RECORDER_ROLES | {
	"VetEdge Front Desk",
}
MANUAL_ACCOUNTING_RESOLUTION_ACTIONS = {
	"refund_required",
	"issue_customer_credit",
	"admin_accounting_correction",
}


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


@frappe.whitelist()
def get_cancellation_resolution_options(consultation_name: str) -> dict:
	require_internal_user()
	can_access_consultation(frappe.session.user, consultation_name, raise_exception=True)
	preflight = build_consultation_cancellation_preflight(consultation_name)
	return {
		"consultation": consultation_name,
		"can_record_resolution": can_record_resolution_for_preflight(preflight)
		and user_can_record_cancellation_resolution(frappe.session.user),
		"allowed_action_options": get_recordable_resolution_options(preflight),
		"existing_resolution": get_consultation_cancellation_resolution(consultation_name),
		"billing_group_summary": preflight.get("billing_group_summary") or {},
	}


@frappe.whitelist()
def get_consultation_cancellation_resolution(consultation_name: str) -> dict | None:
	require_internal_user()
	can_access_consultation(frappe.session.user, consultation_name, raise_exception=True)
	return get_latest_cancellation_resolution(consultation_name)


@frappe.whitelist()
def record_consultation_cancellation_resolution(
	consultation_name: str,
	resolution_action: str,
	reason: str | None = None,
	linked_new_consultation: str | None = None,
	linked_new_appointment: str | None = None,
) -> dict:
	require_internal_user()
	can_access_consultation(frappe.session.user, consultation_name, raise_exception=True)
	validate_user_can_record_cancellation_resolution(frappe.session.user)
	return record_cancellation_resolution_decision(
		consultation_name,
		resolution_action,
		reason=reason,
		linked_new_consultation=linked_new_consultation,
		linked_new_appointment=linked_new_appointment,
	)


@frappe.whitelist()
def retain_payment_and_cancel_consultation(consultation_name: str, reason: str | None = None) -> dict:
	require_internal_user()
	can_access_consultation(frappe.session.user, consultation_name, raise_exception=True)
	validate_user_can_execute_retain_payment_cancellation(frappe.session.user)
	return execute_retain_payment_consultation_cancellation(consultation_name, reason=reason)


@frappe.whitelist()
def execute_consultation_reschedule_resolution(
	consultation_name: str,
	resolution_name: str | None = None,
	appointment_datetime: str | None = None,
	reason: str | None = None,
	create_new_consultation: bool = False,
) -> dict:
	require_internal_user()
	can_access_consultation(frappe.session.user, consultation_name, raise_exception=True)
	validate_user_can_execute_reschedule_cancellation_resolution(frappe.session.user)
	return execute_reschedule_consultation_resolution(
		consultation_name,
		resolution_name=resolution_name,
		appointment_datetime=appointment_datetime,
		reason=reason,
		create_new_consultation=create_new_consultation,
	)


@frappe.whitelist()
def complete_consultation_cancellation_resolution_manually(
	resolution_name: str,
	completion_note: str | None = None,
	reference_document: str | None = None,
) -> dict:
	require_internal_user()
	validate_user_can_complete_manual_accounting_resolution(frappe.session.user)
	if not safe_doctype_exists(CANCELLATION_RESOLUTION_DOCTYPE):
		frappe.throw("Cancellation resolution records are not installed. Please run migrate.", frappe.ValidationError)
	resolution = frappe.get_doc(CANCELLATION_RESOLUTION_DOCTYPE, resolution_name)
	can_access_consultation(frappe.session.user, resolution.consultation, raise_exception=True)
	return complete_manual_accounting_resolution(
		resolution,
		completion_note=completion_note,
		reference_document=reference_document,
	)


@frappe.whitelist()
def approve_consultation_cancellation_resolution(resolution_name: str, note: str | None = None) -> dict:
	return update_consultation_cancellation_resolution_status(resolution_name, "Approved", note=note)


@frappe.whitelist()
def update_consultation_cancellation_resolution_status(resolution_name: str, status: str, note: str | None = None) -> dict:
	require_internal_user()
	validate_user_can_approve_cancellation_resolution(frappe.session.user)
	if status not in {"Approved", "Rejected"}:
		frappe.throw("Only Approved or Rejected status updates are allowed from this action.", frappe.ValidationError)
	if not safe_doctype_exists(CANCELLATION_RESOLUTION_DOCTYPE):
		frappe.throw("Cancellation resolution records are not installed. Please run migrate.", frappe.ValidationError)

	resolution = frappe.get_doc(CANCELLATION_RESOLUTION_DOCTYPE, resolution_name)
	can_access_consultation(frappe.session.user, resolution.consultation, raise_exception=True)
	if resolution.resolution_status in {"Approved", "Completed"}:
		frappe.throw("Approved or completed cancellation resolutions cannot be changed by this action.", frappe.ValidationError)
	if resolution.resolution_status == "Rejected":
		frappe.throw("Rejected cancellation resolutions cannot be changed by this action.", frappe.ValidationError)
	if resolution.resolution_status not in {"Draft", "Pending Review"}:
		frappe.throw("Only Draft or Pending Review cancellation resolutions can be approved or rejected.", frappe.ValidationError)

	resolution.resolution_status = status
	if status == "Approved":
		resolution.approved_by = frappe.session.user
		resolution.approved_on = now_datetime()
	append_resolution_note(resolution, note or f"Resolution {status.lower()} by {frappe.session.user}.")
	resolution.save()
	return serialize_cancellation_resolution(resolution)


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
		"skipped_draft_invoices": cleanup_result["skipped_draft_invoices"],
		"closed_billing_sessions": cleanup_result["closed_billing_sessions"],
		"warnings": preflight.get("warnings") or [],
		"preserved_references": cleanup_result["preserved_references"],
		"preserved_patient_outstanding_invoices": [
			row.get("invoice") or row.get("name")
			for row in preflight.get("outstanding_context") or []
			if row.get("invoice") or row.get("name")
		],
		"message": "Consultation cancelled after safe draft cleanup.",
	}


def execute_retain_payment_consultation_cancellation(consultation_name: str, reason: str | None = None) -> dict:
	preflight = build_consultation_cancellation_preflight(consultation_name)
	resolution = get_valid_retain_payment_resolution_doc(consultation_name)
	validate_retain_payment_cancellation_allowed(preflight, resolution)

	consultation = frappe.get_doc("Veterinary Consultation", consultation_name)
	consultation.status = "Cancelled"
	if reason:
		set_cancellation_reason_if_supported(consultation, reason)
	run_with_retain_payment_cancellation_flag(consultation.save)

	resolution.resolution_status = "Completed"
	if frappe.get_meta(CANCELLATION_RESOLUTION_DOCTYPE).has_field("notes"):
		existing_notes = (resolution.get("notes") or "").strip()
		retain_note = "Payment retained. No refund, credit note, Payment Entry, Stock Entry, or Sales Invoice reversal was created."
		resolution.notes = "\n".join([note for note in (existing_notes, retain_note) if note])
	resolution.save()

	return {
		"status": "success",
		"consultation": consultation.name,
		"consultation_status": consultation.status,
		"resolution": serialize_cancellation_resolution(resolution),
		"resolution_status": resolution.resolution_status,
		"invoices_preserved": [
			row.get("invoice") or row.get("name")
			for row in preflight.get("linked_invoices") or []
			if row.get("invoice") or row.get("name")
		],
		"payments_preserved": True,
		"warnings": preflight.get("warnings") or [],
		"message": "Clinical consultation cancelled. Payment was retained. No accounting reversal was created.",
	}


def execute_reschedule_consultation_resolution(
	consultation_name: str,
	resolution_name: str | None = None,
	appointment_datetime: str | None = None,
	reason: str | None = None,
	create_new_consultation: bool = False,
) -> dict:
	if create_new_consultation:
		frappe.throw(
			"Automatic new consultation creation is not supported for reschedule cancellation resolution yet.",
			frappe.ValidationError,
		)
	if not appointment_datetime:
		frappe.throw("Appointment date/time is required to complete reschedule resolution.", frappe.ValidationError)

	preflight = build_consultation_cancellation_preflight(consultation_name)
	resolution = get_valid_reschedule_resolution_doc(consultation_name, resolution_name=resolution_name)
	validate_reschedule_resolution_allowed(preflight, resolution)

	from vetedge.services.appointment_flow import create_follow_up_from_consultation

	appointment = create_follow_up_from_consultation(
		consultation_name,
		appointment_datetime=appointment_datetime,
		notes=build_reschedule_appointment_notes(resolution, reason),
	)
	appointment_name = appointment.get("name") if isinstance(appointment, dict) else appointment

	resolution.linked_new_appointment = appointment_name
	resolution.resolution_status = "Completed"
	append_resolution_note(
		resolution,
		"Reschedule recorded. Submitted invoices, payments, stock entries, and billing history from the original consultation remain unchanged.",
	)
	if reason:
		append_resolution_note(resolution, reason)
	resolution.save()

	return {
		"status": "success",
		"consultation": consultation_name,
		"consultation_status": frappe.db.get_value("Veterinary Consultation", consultation_name, "status"),
		"resolution": serialize_cancellation_resolution(resolution),
		"resolution_status": resolution.resolution_status,
		"linked_new_appointment": appointment_name,
		"linked_new_consultation": resolution.get("linked_new_consultation"),
		"invoices_preserved": [
			row.get("invoice") or row.get("name")
			for row in preflight.get("linked_invoices") or []
			if row.get("invoice") or row.get("name")
		],
		"payments_preserved": True,
		"message": "Consultation rescheduled. Original invoices and payments were preserved.",
	}


def complete_manual_accounting_resolution(
	resolution,
	completion_note: str | None = None,
	reference_document: str | None = None,
) -> dict:
	validate_manual_accounting_resolution_completion(resolution, completion_note)

	note_lines = [
		f"Manual accounting resolution completed by {frappe.session.user} on {now_datetime()}.",
		completion_note.strip(),
	]
	if reference_document:
		note_lines.append(f"Manual reference: {reference_document.strip()}.")
	note_lines.append(
		"Acknowledgement only. VetEdge did not create or mutate Credit Notes, Payment Entries, Sales Invoices, Stock Entries, refunds, or payment allocations."
	)
	append_resolution_note(resolution, "\n".join(note_lines))
	resolution.resolution_status = "Completed"
	resolution.save()

	return {
		"status": "success",
		"consultation": resolution.get("consultation"),
		"consultation_status": frappe.db.get_value("Veterinary Consultation", resolution.get("consultation"), "status"),
		"resolution": serialize_cancellation_resolution(resolution),
		"resolution_status": resolution.resolution_status,
		"reference_document": reference_document,
		"accounting_documents_preserved": True,
		"message": "Manual accounting resolution recorded. Consultation status and submitted accounting documents were unchanged.",
	}


def run_with_retain_payment_cancellation_flag(callback):
	if not getattr(frappe, "flags", None):
		frappe.flags = frappe._dict()
	previous = getattr(frappe.flags, "vetedge_retain_payment_cancellation", False)
	frappe.flags.vetedge_retain_payment_cancellation = True
	try:
		return callback()
	finally:
		frappe.flags.vetedge_retain_payment_cancellation = previous


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
		"existing_resolution": get_latest_cancellation_resolution(consultation_name),
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
	skipped_draft_invoices: list[dict] = []
	preserved_references: list[dict] = []
	for row in preflight.get("linked_invoices") or []:
		if cint(row.get("docstatus")) != 0:
			preserved_references.append({"invoice": row.get("invoice"), "reason": "non_draft_invoice_preserved"})
			continue
		invoice_name = row.get("invoice") or row.get("name")
		if not invoice_name:
			continue
		if not is_draft_invoice_safe_for_consultation_cleanup(invoice_name, consultation_name):
			skipped_draft_invoices.append({"invoice": invoice_name, "reason": "not_exclusive_to_current_consultation"})
			frappe.throw(
				f"Draft invoice {invoice_name} is not exclusive to this consultation billing group and was not cleaned up.",
				frappe.ValidationError,
			)
		cleanup_draft_invoice_for_consultation(invoice_name, consultation_name)
		cleaned_draft_invoices.append(invoice_name)

	closed_billing_sessions = close_safe_draft_billing_sessions(consultation_name)
	return {
		"cleaned_draft_invoices": cleaned_draft_invoices,
		"skipped_draft_invoices": skipped_draft_invoices,
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
	try:
		run_with_billing_core_sync_flag(lambda: delete_safe_draft_sales_invoice(invoice_name, consultation_name))
	except frappe.PermissionError:
		frappe.throw(
			f"Draft invoice {invoice_name} could not be cleaned automatically. Please ask Accounts/Admin to review it.",
			frappe.ValidationError,
		)


def delete_safe_draft_sales_invoice(invoice_name: str, consultation_name: str) -> None:
	if not is_draft_invoice_safe_for_consultation_cleanup(invoice_name, consultation_name):
		frappe.throw(
			f"Draft invoice {invoice_name} could not be cleaned automatically. Please ask Accounts/Admin to review it.",
			frappe.ValidationError,
		)
	# System-generated draft invoice cleanup for a VetEdge-cancelled consultation; submitted invoices are never mutated.
	frappe.delete_doc("Sales Invoice", invoice_name, ignore_permissions=True)


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
				"display_label": f"Invoice {invoice_name}",
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
		label = row.get("display_label") or f"Invoice {row.get('invoice')}"
		if docstatus == 0:
			warnings.append(
				{
					"type": "draft_invoice",
					"invoice": row.get("invoice"),
					"display_label": label,
					"message": f"{label} is a draft invoice and will be cleaned up if cancellation proceeds.",
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
					"display_label": label,
					"message": f"{label} has payment recorded and needs a financial resolution before cancellation.",
				}
			)
		else:
			blockers.append(
				{
					"type": "submitted_invoice",
					"invoice": row.get("invoice"),
					"display_label": label,
					"message": f"{label} is submitted and must be handled by accounts/admin before cancellation.",
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
		label = get_linked_document_display_label("Veterinary Lab Order", row)
		target = blockers if row.get("status") in LAB_FINAL_STATUSES or cint(row.get("docstatus")) == 1 else warnings
		target.append(
			{
				"type": "linked_lab_order",
				"document": row.get("name"),
				"display_label": label,
				"status": row.get("status"),
				"message": f"{label} is {row.get('status') or 'active'} and must be resolved before cancellation.",
			}
		)


def get_linked_vaccinations(consultation_name: str) -> list[dict]:
	return get_linked_docs(
		"Veterinary Vaccination Record",
		{"linked_consultation": consultation_name},
		["name", "status", "docstatus", "vaccine", "vaccine_name", "linked_invoice", "sales_invoice", "stock_entry"],
	)


def add_vaccination_blockers(blockers: list[dict], warnings: list[dict], rows: list[dict]) -> None:
	for row in rows:
		if row.get("status") in {"Cancelled"} or cint(row.get("docstatus")) == 2:
			continue
		label = get_linked_document_display_label("Veterinary Vaccination Record", row)
		target = blockers if row.get("status") in VACCINATION_FINAL_STATUSES or cint(row.get("docstatus")) == 1 else warnings
		target.append(
			{
				"type": "linked_vaccination",
				"document": row.get("name"),
				"display_label": label,
				"status": row.get("status"),
				"message": f"{label} is {row.get('status') or 'active'} and must be resolved before cancellation.",
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
				"display_label": get_planned_treatment_display_label(row),
			}
		)
	return rows


def get_planned_treatment_display_label(row) -> str:
	source_type = row.get("source_type")
	source_document = row.get("source_document")
	source_detail = row.get("source_detail_name")
	description = row.get("description")
	item = row.get("item") or row.get("item_code")

	if source_type == "Consultation" or normalize_label_key(source_detail) in {"default consultation fee", "consultation fee"}:
		return "Consultation Fee"
	if source_type == "Registration" or normalize_label_key(source_detail) == "registration fee":
		return "Registration Fee"
	if source_type == "Lab Order":
		return f"Lab Order: {source_document or get_best_text(description, item, source_detail, row.get('name'))}"
	if source_type == "Vaccination":
		return f"Vaccination: {get_best_text(description, item, source_detail, source_document)}"
	if source_type:
		return f"{source_type}: {get_best_text(description, item, source_detail, source_document)}"
	if item or description:
		return f"Treatment: {get_best_text(description, item)}"
	return "Treatment"


def get_linked_document_display_label(doctype: str, row: dict) -> str:
	name = row.get("name") or row.get("document")
	if doctype == "Veterinary Lab Order":
		return f"Lab Order: {name}"
	if doctype == "Veterinary Vaccination Record":
		vaccine = row.get("vaccine") or row.get("vaccine_name")
		return f"Vaccination: {vaccine or name}"
	if doctype == "Veterinary Hospitalisation":
		return f"Hospitalisation {name}"
	return f"{doctype} {name}"


def get_best_text(*values) -> str:
	for value in values:
		if value:
			return humanize_cancellation_label(value)
	return ""


def humanize_cancellation_label(value) -> str:
	text = str(value or "").strip()
	if not text:
		return ""
	normalized = normalize_label_key(text)
	if normalized in {"consultation fee", "default consultation fee", "default_consultation_fee"}:
		return "Consultation Fee"
	if normalized in {"registration fee", "default registration fee", "registration_fee"}:
		return "Registration Fee"
	return text.replace("_", " ").replace("-", " ").title() if text.lower() == text or "_" in text else text


def normalize_label_key(value) -> str:
	return str(value or "").strip().replace("_", " ").replace("-", " ").lower()


def add_planned_treatment_warnings(warnings: list[dict], rows: list[dict]) -> None:
	for row in rows:
		source_type = row.get("source_type")
		source_document = row.get("source_document")
		if not source_type and not source_document:
			continue
		label = row.get("display_label") or get_planned_treatment_display_label(row)
		warnings.append(
			{
				"type": "source_linked_planned_treatment",
				"document": row.get("name"),
				"display_label": label,
				"source_type": source_type,
				"source_document": source_document,
				"message": (
					f"{label} is linked to "
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
		label = get_linked_document_display_label("Veterinary Hospitalisation", row)
		target = blockers if row.get("status") in HOSPITALISATION_ACTIVE_STATUSES or cint(row.get("docstatus")) == 1 else warnings
		target.append(
			{
				"type": "linked_hospitalisation",
				"document": row.get("name"),
				"display_label": label,
				"status": row.get("status"),
				"message": f"{label} is {row.get('status') or 'active'} and must be resolved before cancellation.",
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
		label = f"Stock Entry {row.get('name')}"
		target = blockers if cint(row.get("docstatus")) == 1 else warnings
		target.append(
			{
				"type": "linked_stock_entry",
				"document": row.get("name"),
				"display_label": label,
				"docstatus": cint(row.get("docstatus")),
				"message": f"{label} must be handled by stock/accounts before cancellation.",
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


def record_cancellation_resolution_decision(
	consultation_name: str,
	resolution_action: str,
	reason: str | None = None,
	linked_new_consultation: str | None = None,
	linked_new_appointment: str | None = None,
) -> dict:
	preflight = build_consultation_cancellation_preflight(consultation_name)
	if not can_record_resolution_for_preflight(preflight):
		frappe.throw(
			"Cancellation resolution can only be recorded when the consultation is blocked by submitted or paid billing.",
			frappe.ValidationError,
		)
	action_key = normalize_resolution_action(resolution_action)
	if action_key not in FINANCIAL_RESOLUTION_ACTIONS or action_key not in (preflight.get("allowed_actions") or []):
		frappe.throw("Select a valid cancellation resolution action for this consultation.", frappe.ValidationError)
	if not safe_doctype_exists(CANCELLATION_RESOLUTION_DOCTYPE):
		frappe.throw("Cancellation resolution records are not installed. Please run migrate.", frappe.ValidationError)

	consultation = frappe.get_doc("Veterinary Consultation", consultation_name)
	existing = get_open_cancellation_resolution_doc(consultation_name)
	if existing and existing.get("resolution_status") in {"Approved", "Completed"}:
		frappe.throw("An approved or completed cancellation resolution already exists for this consultation.", frappe.ValidationError)
	doc = existing or frappe.new_doc(CANCELLATION_RESOLUTION_DOCTYPE)
	populate_cancellation_resolution_doc(
		doc,
		consultation,
		preflight,
		action_key,
		reason=reason,
		linked_new_consultation=linked_new_consultation,
		linked_new_appointment=linked_new_appointment,
	)
	if existing:
		doc.save()
	else:
		doc.insert()
	return serialize_cancellation_resolution(doc)


def get_valid_retain_payment_resolution_doc(consultation_name: str):
	resolution = get_open_cancellation_resolution_doc(consultation_name)
	if not resolution:
		frappe.throw(
			"Record a Retain Payment / Clinical Cancellation Only resolution before cancelling this paid consultation.",
			frappe.ValidationError,
		)
	if resolution.get("resolution_action_key") != "retain_payment_clinical_cancel_only":
		frappe.throw(
			"Only a Retain Payment / Clinical Cancellation Only resolution can use retained-payment cancellation.",
			frappe.ValidationError,
		)
	if resolution.get("resolution_status") != "Approved":
		frappe.throw(
			"Retained-payment cancellation requires an Approved resolution decision.",
			frappe.ValidationError,
		)
	return resolution


def get_valid_reschedule_resolution_doc(consultation_name: str, resolution_name: str | None = None):
	resolution = frappe.get_doc(CANCELLATION_RESOLUTION_DOCTYPE, resolution_name) if resolution_name else get_open_cancellation_resolution_doc(consultation_name)
	if not resolution:
		frappe.throw(
			"Record a Reschedule Consultation resolution before completing reschedule.",
			frappe.ValidationError,
		)
	if resolution.get("consultation") != consultation_name:
		frappe.throw("Cancellation resolution does not belong to this consultation.", frappe.ValidationError)
	if resolution.get("resolution_action_key") != "reschedule_consultation":
		frappe.throw(
			"Only a Reschedule Consultation resolution can complete rescheduling.",
			frappe.ValidationError,
		)
	if resolution.get("resolution_status") != "Approved":
		frappe.throw(
			"Reschedule consultation requires an Approved resolution decision.",
			frappe.ValidationError,
		)
	return resolution


def validate_retain_payment_cancellation_allowed(preflight: dict, resolution) -> None:
	if preflight.get("can_cancel"):
		frappe.throw(
			"Use normal safe cancellation for consultations without submitted or paid billing blockers.",
			frappe.ValidationError,
		)
	blocker_types = {row.get("type") for row in preflight.get("blockers") or []}
	if not blocker_types.intersection({"paid_invoice", "submitted_invoice"}):
		frappe.throw(
			"Retained-payment cancellation is only available for consultations blocked by submitted or paid billing.",
			frappe.ValidationError,
		)
	summary = preflight.get("billing_group_summary") or {}
	if cint(summary.get("submitted_invoice_count")) <= 0:
		frappe.throw("A submitted consultation invoice is required before retaining payment.", frappe.ValidationError)
	if flt(summary.get("paid_amount")) <= 0:
		frappe.throw("Payment must exist before using retained-payment cancellation.", frappe.ValidationError)
	if resolution.get("consultation") != preflight.get("consultation"):
		frappe.throw("Cancellation resolution does not belong to this consultation.", frappe.ValidationError)


def validate_reschedule_resolution_allowed(preflight: dict, resolution) -> None:
	if preflight.get("can_cancel"):
		frappe.throw(
			"Use normal safe cancellation for consultations without submitted or paid billing blockers.",
			frappe.ValidationError,
		)
	blocker_types = {row.get("type") for row in preflight.get("blockers") or []}
	if not blocker_types.intersection({"paid_invoice", "submitted_invoice"}):
		frappe.throw(
			"Reschedule resolution is only available for consultations blocked by submitted or paid billing.",
			frappe.ValidationError,
		)
	if resolution.get("consultation") != preflight.get("consultation"):
		frappe.throw("Cancellation resolution does not belong to this consultation.", frappe.ValidationError)


def validate_manual_accounting_resolution_completion(resolution, completion_note: str | None) -> None:
	if resolution.get("resolution_action_key") not in MANUAL_ACCOUNTING_RESOLUTION_ACTIONS:
		frappe.throw(
			"Only refund, customer credit, or admin accounting correction resolutions can be manually completed by this action.",
			frappe.ValidationError,
		)
	if resolution.get("resolution_status") != "Approved":
		frappe.throw("Only Approved accounting resolution decisions can be marked completed.", frappe.ValidationError)
	if not completion_note or not completion_note.strip():
		frappe.throw("Completion note is required before marking this accounting resolution completed.", frappe.ValidationError)


def build_reschedule_appointment_notes(resolution, reason: str | None = None) -> str:
	parts = [
		f"Rescheduled from consultation {resolution.get('consultation')}.",
		"Original submitted invoices and payments remain unchanged.",
	]
	if reason:
		parts.append(reason)
	elif resolution.get("reason"):
		parts.append(resolution.get("reason"))
	return "\n".join(parts)


def populate_cancellation_resolution_doc(
	doc,
	consultation,
	preflight: dict,
	action_key: str,
	reason: str | None = None,
	linked_new_consultation: str | None = None,
	linked_new_appointment: str | None = None,
) -> None:
	summary = preflight.get("billing_group_summary") or {}
	doc.consultation = consultation.name
	doc.patient = consultation.get("patient")
	doc.customer = consultation.get("primary_owner") or consultation.get("customer")
	doc.branch = consultation.get("service_branch") or consultation.get("branch")
	doc.company = consultation.get("company")
	doc.resolution_action_key = action_key
	doc.resolution_action = RESOLUTION_ACTION_LABELS.get(action_key, action_key.replace("_", " ").title())
	doc.resolution_status = doc.get("resolution_status") or "Pending Review"
	doc.reason = reason
	doc.selected_by = frappe.session.user
	doc.selected_on = now_datetime()
	doc.linked_new_consultation = linked_new_consultation
	doc.linked_new_appointment = linked_new_appointment
	doc.billing_group_paid_amount = flt(summary.get("paid_amount"))
	doc.billing_group_outstanding_amount = flt(summary.get("outstanding_amount"))
	doc.related_invoices = json.dumps(build_resolution_invoice_snapshot(preflight.get("linked_invoices") or []), default=str)
	doc.notes = "Resolution decision only. No refund, credit note, Payment Entry, Stock Entry, or Sales Invoice reversal was created."


def append_resolution_note(resolution, note: str | None) -> None:
	if not note or not frappe.get_meta(CANCELLATION_RESOLUTION_DOCTYPE).has_field("notes"):
		return
	existing_notes = (resolution.get("notes") or "").strip()
	resolution.notes = "\n".join([value for value in (existing_notes, note.strip()) if value])


def build_resolution_invoice_snapshot(invoices: list[dict]) -> list[dict]:
	return [
		{
			"invoice": row.get("invoice") or row.get("name"),
			"docstatus": cint(row.get("docstatus")),
			"status": row.get("status"),
			"payment_state": row.get("payment_state"),
			"grand_total": flt(row.get("grand_total")),
			"paid_amount": flt(row.get("paid_amount")),
			"outstanding_amount": flt(row.get("outstanding_amount")),
			"billing_session": row.get("billing_session"),
			"relation_type": row.get("relation_type"),
		}
		for row in invoices
		if row.get("invoice") or row.get("name")
	]


def can_record_resolution_for_preflight(preflight: dict) -> bool:
	if preflight.get("can_cancel"):
		return False
	blocker_types = {row.get("type") for row in preflight.get("blockers") or []}
	return bool(
		blocker_types.intersection({"paid_invoice", "submitted_invoice"})
		or flt((preflight.get("billing_group_summary") or {}).get("paid_amount")) > 0
	)


def get_recordable_resolution_options(preflight: dict) -> list[dict]:
	if not can_record_resolution_for_preflight(preflight):
		return []
	return get_cancellation_action_options(
		[action for action in preflight.get("allowed_actions") or [] if action in FINANCIAL_RESOLUTION_ACTIONS]
	)


def normalize_resolution_action(action: str | None) -> str:
	if not action:
		return ""
	if action in FINANCIAL_RESOLUTION_ACTIONS:
		return action
	reverse = {label: key for key, label in RESOLUTION_ACTION_LABELS.items()}
	return reverse.get(action, str(action).strip().lower().replace(" ", "_"))


def get_open_cancellation_resolution_doc(consultation_name: str):
	if not safe_doctype_exists(CANCELLATION_RESOLUTION_DOCTYPE):
		return None
	rows = frappe.get_all(
		CANCELLATION_RESOLUTION_DOCTYPE,
		filters={"consultation": consultation_name, "resolution_status": ["in", ["Draft", "Pending Review", "Approved", "Completed"]]},
		fields=["name", "resolution_status"],
		order_by="modified desc",
		limit=1,
	)
	if not rows:
		return None
	return frappe.get_doc(CANCELLATION_RESOLUTION_DOCTYPE, rows[0].name)


def get_latest_cancellation_resolution(consultation_name: str) -> dict | None:
	if not safe_doctype_exists(CANCELLATION_RESOLUTION_DOCTYPE):
		return None
	rows = frappe.get_all(
		CANCELLATION_RESOLUTION_DOCTYPE,
		filters={"consultation": consultation_name},
		fields=[
			"name",
			"consultation",
			"resolution_action",
			"resolution_action_key",
			"resolution_status",
			"reason",
			"selected_by",
			"selected_on",
			"approved_by",
			"approved_on",
			"linked_new_consultation",
			"linked_new_appointment",
			"billing_group_paid_amount",
			"billing_group_outstanding_amount",
			"related_invoices",
		],
		order_by="modified desc",
		limit=1,
	)
	if not rows:
		return None
	return serialize_cancellation_resolution(frappe._dict(rows[0]))


def serialize_cancellation_resolution(doc) -> dict:
	return {
		"name": doc.get("name"),
		"consultation": doc.get("consultation"),
		"resolution_action": doc.get("resolution_action"),
		"resolution_action_key": doc.get("resolution_action_key"),
		"resolution_status": doc.get("resolution_status"),
		"reason": doc.get("reason"),
		"selected_by": doc.get("selected_by"),
		"selected_on": doc.get("selected_on"),
		"approved_by": doc.get("approved_by"),
		"approved_on": doc.get("approved_on"),
		"linked_new_consultation": doc.get("linked_new_consultation"),
		"linked_new_appointment": doc.get("linked_new_appointment"),
		"billing_group_paid_amount": flt(doc.get("billing_group_paid_amount")),
		"billing_group_outstanding_amount": flt(doc.get("billing_group_outstanding_amount")),
		"related_invoices": parse_json_field(doc.get("related_invoices")),
	}


def parse_json_field(value):
	if not value:
		return []
	if isinstance(value, (list, dict)):
		return value
	try:
		return json.loads(value)
	except Exception:
		return value


def validate_user_can_record_cancellation_resolution(user: str) -> None:
	if not user_can_record_cancellation_resolution(user):
		frappe.throw("You do not have permission to record consultation cancellation resolution decisions.", frappe.PermissionError)


def user_can_record_cancellation_resolution(user: str) -> bool:
	get_roles = getattr(frappe, "get_roles", None)
	if not get_roles:
		return False
	return bool(set(get_roles(user)) & RESOLUTION_RECORDER_ROLES)


def validate_user_can_execute_retain_payment_cancellation(user: str) -> None:
	if not user_can_execute_retain_payment_cancellation(user):
		frappe.throw("You do not have permission to cancel a consultation while retaining payment.", frappe.PermissionError)


def user_can_execute_retain_payment_cancellation(user: str) -> bool:
	get_roles = getattr(frappe, "get_roles", None)
	if not get_roles:
		return False
	return bool(set(get_roles(user)) & RETAIN_PAYMENT_EXECUTOR_ROLES)


def validate_user_can_approve_cancellation_resolution(user: str) -> None:
	if not user_can_approve_cancellation_resolution(user):
		frappe.throw("You do not have permission to approve consultation cancellation resolutions.", frappe.PermissionError)


def user_can_approve_cancellation_resolution(user: str) -> bool:
	get_roles = getattr(frappe, "get_roles", None)
	if not get_roles:
		return False
	return bool(set(get_roles(user)) & RETAIN_PAYMENT_EXECUTOR_ROLES)


def validate_user_can_execute_reschedule_cancellation_resolution(user: str) -> None:
	if not user_can_execute_reschedule_cancellation_resolution(user):
		frappe.throw("You do not have permission to execute consultation reschedule resolutions.", frappe.PermissionError)


def user_can_execute_reschedule_cancellation_resolution(user: str) -> bool:
	get_roles = getattr(frappe, "get_roles", None)
	if not get_roles:
		return False
	return bool(set(get_roles(user)) & RESCHEDULE_EXECUTOR_ROLES)


def validate_user_can_complete_manual_accounting_resolution(user: str) -> None:
	if not user_can_complete_manual_accounting_resolution(user):
		frappe.throw("You do not have permission to complete manual accounting resolution decisions.", frappe.PermissionError)


def user_can_complete_manual_accounting_resolution(user: str) -> bool:
	get_roles = getattr(frappe, "get_roles", None)
	if not get_roles:
		return False
	return bool(set(get_roles(user)) & RETAIN_PAYMENT_EXECUTOR_ROLES)


def safe_doctype_exists(doctype: str) -> bool:
	try:
		return bool(frappe.db.exists("DocType", doctype))
	except Exception:
		return False
