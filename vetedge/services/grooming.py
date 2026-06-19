from __future__ import annotations

from datetime import datetime

import frappe
from frappe.utils import get_datetime, getdate, now_datetime, nowdate

from vetedge.services.billing import PAID_STATUS, build_invoice_item, get_invoice_payment_status, is_active_sales_invoice, validate_sales_item
from vetedge.services.consultation_flow import get_document_title, get_user_full_name, validate_practitioner_branch_access, validate_user_branch_access
from vetedge.services.permissions import (
	can_create_grooming_session,
	can_manage_grooming_appointments,
	can_manage_grooming_billing,
	can_progress_grooming_session,
	get_current_user,
)
from vetedge.services.feature_flags import is_enabled
from vetedge.services.notifications import emit_notification_event
from vetedge.services.portal_access import require_internal_user
from vetedge.services.registration_billing import get_billing_cost_center, get_default_company

GROOMING_SERVICE_DOCTYPE = "Pet Grooming Service"
GROOMING_APPOINTMENT_DOCTYPE = "Pet Grooming Appointment"
GROOMING_SESSION_DOCTYPE = "Pet Grooming Session"

GROOMING_APPOINTMENT_STATUSES = {
	"Scheduled",
	"Confirmed",
	"Checked In",
	"In Progress",
	"Completed",
	"Cancelled",
	"No Show",
}

VALID_APPOINTMENT_STATUS_TRANSITIONS = {
	"Scheduled": {"Confirmed", "Cancelled", "No Show"},
	"Confirmed": {"Checked In", "In Progress", "Cancelled", "No Show"},
	"Checked In": {"In Progress", "Cancelled"},
	"In Progress": {"Completed", "Cancelled"},
	"Completed": set(),
	"Cancelled": set(),
	"No Show": set(),
}

GROOMING_SESSION_STATUSES = {
	"Draft",
	"Awaiting Payment",
	"Pending Grooming",
	"In Progress",
	"Completed",
	"Cancelled",
}

VALID_SESSION_STATUS_TRANSITIONS = {
	"Draft": {"Awaiting Payment", "Pending Grooming", "In Progress", "Cancelled"},
	"Awaiting Payment": {"Pending Grooming", "In Progress", "Cancelled"},
	"Pending Grooming": {"In Progress", "Cancelled"},
	"In Progress": {"Completed", "Cancelled"},
	"Completed": set(),
	"Cancelled": set(),
}

TERMINAL_GROOMING_STATUSES = {"Completed", "Cancelled"}
GROOMING_APPOINTMENT_SYSTEM_FIELDS = {"grooming_appointment_title", "groomer_name", "linked_invoice", "modified", "modified_by"}
GROOMING_SESSION_SYSTEM_FIELDS = {"grooming_session_title", "groomer_name", "linked_invoice", "modified", "modified_by"}


def ensure_grooming_enabled() -> None:
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return
	if not is_enabled("grooming"):
		frappe.throw("Grooming is not enabled in Veterinary Settings.", frappe.ValidationError)



def is_grooming_billing_enabled() -> bool:
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return False
	get_meta = getattr(frappe, "get_meta", None)
	if not get_meta:
		return False
	meta = get_meta("Veterinary Settings")
	if not meta.has_field("enable_grooming_billing"):
		return False
	return bool(frappe.db.get_single_value("Veterinary Settings", "enable_grooming_billing"))



def require_grooming_appointment_enabled() -> bool:
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return False
	meta = frappe.get_meta("Veterinary Settings")
	if not meta.has_field("require_grooming_appointment"):
		return False
	return bool(frappe.db.get_single_value("Veterinary Settings", "require_grooming_appointment"))



def allow_direct_grooming_session() -> bool:
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return True
	meta = frappe.get_meta("Veterinary Settings")
	if not meta.has_field("allow_grooming_without_consultation"):
		return True
	return bool(frappe.db.get_single_value("Veterinary Settings", "allow_grooming_without_consultation"))



def enforce_terminal_grooming_read_only(doc, previous, system_fields: set[str], label: str) -> None:
	if not previous or previous.status not in TERMINAL_GROOMING_STATUSES:
		return
	allowed_fields = set(system_fields)
	for field in getattr(doc.meta, "fields", []) or []:
		if getattr(field, "allow_on_submit", 0):
			allowed_fields.add(field.fieldname)
	changed_fields = []
	for field in getattr(doc.meta, "fields", []) or []:
		fieldname = field.fieldname
		if not fieldname or fieldname in allowed_fields:
			continue
		if doc.get(fieldname) != previous.get(fieldname):
			changed_fields.append(field.label or fieldname)
	if changed_fields:
		frappe.throw(
			f"{label} records in {previous.status} status are read-only. Only post-submit editable fields can still be updated.",
			frappe.ValidationError,
		)



def validate_grooming_service(doc) -> None:
	ensure_grooming_enabled()
	if not doc.service_name:
		frappe.throw("Service Name is required for Pet Grooming Service.", frappe.ValidationError)
	doc.service_name = str(doc.service_name).strip()
	if doc.service_code:
		doc.service_code = str(doc.service_code).strip().upper()
	if doc.default_item:
		validate_sales_item(doc.default_item, "Default Grooming Item", allow_stock=False)
	if doc.get("default_rate") is not None and float(doc.default_rate or 0) < 0:
		frappe.throw("Default Rate cannot be negative.", frappe.ValidationError)



def validate_grooming_appointment(doc) -> None:
	ensure_grooming_enabled()
	previous = doc.get_doc_before_save() if getattr(doc, "get_doc_before_save", None) else None
	if not doc.status:
		doc.status = "Scheduled"
	validate_grooming_appointment_status(doc, previous)
	validate_grooming_appointment_completion(doc, previous)
	resolve_grooming_context(doc)
	if not doc.scheduled_datetime:
		frappe.throw("Scheduled Datetime is required for Pet Grooming Appointment.", frappe.ValidationError)
	get_datetime(doc.scheduled_datetime)
	validate_service_branch(doc.service_branch, practitioner=doc.groomer)
	set_grooming_appointment_title(doc)
	enforce_terminal_grooming_read_only(doc, previous, GROOMING_APPOINTMENT_SYSTEM_FIELDS, "Pet Grooming Appointment")



def validate_grooming_appointment_status(doc, previous=None) -> None:
	if doc.status not in GROOMING_APPOINTMENT_STATUSES:
		frappe.throw(f"Invalid grooming appointment status: {doc.status}", frappe.ValidationError)
	if not previous or previous.status == doc.status:
		return
	allowed = VALID_APPOINTMENT_STATUS_TRANSITIONS.get(previous.status, set())
	if doc.status not in allowed:
		frappe.throw(
			f"Grooming appointment status cannot move from {previous.status} to {doc.status}.",
			frappe.ValidationError,
		)
	can_manage_grooming_appointments(get_current_user(), doc, raise_exception=True)


def validate_grooming_appointment_completion(doc, previous=None) -> None:
	if doc.status != "Completed":
		return
	if previous and previous.status == "Completed":
		return
	if not doc.name or str(doc.name).startswith("new-"):
		frappe.throw(
			"A Grooming Appointment can only be completed through a completed Pet Grooming Session.",
			frappe.ValidationError,
		)

	completed_session = frappe.get_all(
		GROOMING_SESSION_DOCTYPE,
		filters={"appointment": doc.name, "status": "Completed"},
		fields=["name"],
		limit=1,
	)
	if completed_session:
		return

	frappe.throw(
		"A Grooming Appointment can only be completed through a completed Pet Grooming Session.",
		frappe.ValidationError,
	)



def validate_grooming_session(doc) -> None:
	ensure_grooming_enabled()
	previous = doc.get_doc_before_save() if getattr(doc, "get_doc_before_save", None) else None
	if not doc.status:
		doc.status = "Draft"
	validate_grooming_session_status(doc, previous)
	resolve_grooming_context(doc, session_mode=True)
	validate_direct_session_allowed(doc)
	doc.status = get_grooming_session_workflow_status(doc)
	if doc.status in {"In Progress", "Completed"} and not doc.start_time:
		doc.start_time = now_datetime()
	if doc.status == "Completed" and not doc.end_time:
		doc.end_time = now_datetime()
	if doc.start_time:
		get_datetime(doc.start_time)
	if doc.end_time:
		end_time = get_datetime(doc.end_time)
		if doc.start_time and end_time < get_datetime(doc.start_time):
			frappe.throw("End Time cannot be earlier than Start Time.", frappe.ValidationError)
	if doc.status == "Completed" and not doc.groomer:
		frappe.throw("Groomer is required before completing a grooming session.", frappe.ValidationError)
	validate_service_branch(doc.service_branch, practitioner=doc.groomer)
	set_grooming_session_title(doc)
	enforce_terminal_grooming_read_only(doc, previous, GROOMING_SESSION_SYSTEM_FIELDS, "Pet Grooming Session")



def validate_grooming_session_status(doc, previous=None) -> None:
	if doc.status not in GROOMING_SESSION_STATUSES:
		frappe.throw(f"Invalid grooming session status: {doc.status}", frappe.ValidationError)
	if not previous or previous.status == doc.status:
		return
	allowed = VALID_SESSION_STATUS_TRANSITIONS.get(previous.status, set())
	if doc.status not in allowed:
		frappe.throw(
			f"Grooming session status cannot move from {previous.status} to {doc.status}.",
			frappe.ValidationError,
		)
	if doc.status in {"In Progress", "Completed", "Cancelled"}:
		can_progress_grooming_session(get_current_user(), doc, raise_exception=True)



def resolve_grooming_context(doc, session_mode: bool = False) -> None:
	if session_mode and doc.appointment:
		appointment = frappe.db.get_value(
			GROOMING_APPOINTMENT_DOCTYPE,
			doc.appointment,
			["patient", "primary_owner", "service_branch", "grooming_service", "groomer", "linked_invoice"],
			as_dict=True,
		)
		if not appointment:
			frappe.throw("Pet Grooming Session must reference a valid Pet Grooming Appointment.", frappe.ValidationError)
		doc.patient = appointment.patient
		doc.primary_owner = appointment.primary_owner
		doc.service_branch = appointment.service_branch
		doc.grooming_service = appointment.grooming_service
		if not doc.groomer and appointment.groomer:
			doc.groomer = appointment.groomer
		if not doc.linked_invoice and appointment.linked_invoice:
			doc.linked_invoice = appointment.linked_invoice

	if not doc.patient:
		frappe.throw("Patient is required.", frappe.ValidationError)
	if not doc.grooming_service:
		frappe.throw("Grooming Service is required.", frappe.ValidationError)

	patient = frappe.db.get_value(
		"Veterinary Patient",
		doc.patient,
		["primary_owner", "default_branch"],
		as_dict=True,
	)
	if not patient:
		frappe.throw("A valid Veterinary Patient is required.", frappe.ValidationError)
	if not doc.primary_owner:
		doc.primary_owner = patient.primary_owner
	if not doc.service_branch:
		doc.service_branch = patient.default_branch
	if not doc.primary_owner:
		frappe.throw("Patient must have a Primary Owner before grooming can be scheduled.", frappe.ValidationError)
	if not doc.service_branch:
		frappe.throw("Service Branch is required.", frappe.ValidationError)

	service = frappe.db.get_value(
		GROOMING_SERVICE_DOCTYPE,
		doc.grooming_service,
		["is_active", "default_item", "default_rate"],
		as_dict=True,
	)
	if not service:
		frappe.throw("A valid Pet Grooming Service is required.", frappe.ValidationError)
	if cint_bool(service.is_active) is False:
		frappe.throw(f"Grooming Service {doc.grooming_service} is inactive.", frappe.ValidationError)



def validate_direct_session_allowed(doc) -> None:
	if doc.appointment:
		return
	if require_grooming_appointment_enabled():
		frappe.throw("A Grooming Appointment is required before starting a Pet Grooming Session.", frappe.ValidationError)
	if not allow_direct_grooming_session():
		frappe.throw("Direct grooming sessions are disabled in Veterinary Settings.", frappe.ValidationError)



def get_grooming_session_workflow_status(doc) -> str:
	if doc.status in {"Completed", "Cancelled", "In Progress"}:
		return doc.status
	if not is_grooming_billing_enabled():
		return "Draft"
	if not doc.linked_invoice:
		return "Draft"
	invoice = frappe.get_doc("Sales Invoice", doc.linked_invoice)
	if invoice.docstatus == 2:
		return "Draft"
	if get_invoice_payment_status(invoice) != PAID_STATUS:
		return "Awaiting Payment"
	return "Pending Grooming"



def sync_grooming_session_workflow_status(session_name: str) -> None:
	if not session_name:
		return
	record = frappe.get_doc(GROOMING_SESSION_DOCTYPE, session_name)
	status = get_grooming_session_workflow_status(record)
	if status != record.status:
		frappe.db.set_value(GROOMING_SESSION_DOCTYPE, record.name, "status", status, update_modified=False)



def validate_service_branch(service_branch: str | None, practitioner: str | None = None) -> None:
	if not service_branch:
		return
	validate_user_branch_access(service_branch)
	validate_practitioner_branch_access(practitioner, service_branch)



def set_grooming_appointment_title(doc) -> None:
	patient_title = get_document_title("Veterinary Patient", doc.patient) or doc.patient
	service_title = get_document_title(GROOMING_SERVICE_DOCTYPE, doc.grooming_service) or doc.grooming_service
	parts = [patient_title, service_title]
	if doc.scheduled_datetime:
		parts.append(str(get_datetime(doc.scheduled_datetime).strftime("%Y-%m-%d %H:%M")))
	if doc.service_branch:
		parts.append(doc.service_branch)
	doc.grooming_appointment_title = " - ".join(part for part in parts if part)
	if doc.groomer:
		doc.groomer_name = get_user_full_name(doc.groomer)



def set_grooming_session_title(doc) -> None:
	patient_title = get_document_title("Veterinary Patient", doc.patient) or doc.patient
	service_title = get_document_title(GROOMING_SERVICE_DOCTYPE, doc.grooming_service) or doc.grooming_service
	parts = [patient_title, service_title, "Session"]
	if doc.start_time:
		parts.append(str(get_datetime(doc.start_time).strftime("%Y-%m-%d %H:%M")))
	elif doc.end_time:
		parts.append(str(get_datetime(doc.end_time).strftime("%Y-%m-%d %H:%M")))
	if doc.service_branch:
		parts.append(doc.service_branch)
	doc.grooming_session_title = " - ".join(part for part in parts if part)
	if doc.groomer:
		doc.groomer_name = get_user_full_name(doc.groomer)



def get_grooming_service_billing_defaults(service_name: str) -> tuple[str | None, float | None]:
	service = frappe.db.get_value(GROOMING_SERVICE_DOCTYPE, service_name, ["default_item", "default_rate"], as_dict=True) or {}
	return service.get("default_item"), service.get("default_rate")



def is_draft_sales_invoice(invoice: str | None) -> bool:
	return bool(invoice and frappe.db.get_value("Sales Invoice", invoice, "docstatus") == 0)



def ensure_grooming_invoice_item(invoice, item_code: str, cost_center: str, rate=None) -> str:
	item_payload = build_invoice_item(item_code, 1, None, rate, cost_center)
	existing_row = next((row for row in (invoice.items or []) if row.item_code == item_code), None)
	if existing_row:
		existing_row.qty = item_payload["qty"]
		existing_row.uom = item_payload["uom"]
		existing_row.rate = item_payload["rate"]
		existing_row.amount = item_payload["amount"]
		existing_row.cost_center = item_payload["cost_center"]
	else:
		invoice.append("items", item_payload)
	invoice.save(ignore_permissions=True)
	return invoice.name



def set_grooming_invoice_links(session_doc, invoice_name: str | None) -> None:
	if not invoice_name:
		return
	session_doc.linked_invoice = invoice_name
	if session_doc.appointment:
		frappe.db.set_value(GROOMING_APPOINTMENT_DOCTYPE, session_doc.appointment, "linked_invoice", invoice_name, update_modified=False)



def create_grooming_invoice(session_doc) -> tuple[str | None, bool]:
	if not is_grooming_billing_enabled():
		return None, False
	if use_billing_core_for_grooming():
		from vetedge.services.billing_core import sync_source_to_billing_session

		result = sync_source_to_billing_session(GROOMING_SESSION_DOCTYPE, session_doc.name)
		return result.get("invoice"), bool(result.get("created"))
	item_code, default_rate = get_grooming_service_billing_defaults(session_doc.grooming_service)
	if not item_code:
		frappe.throw("Grooming Service must have a Default Item before billing can be created.", frappe.ValidationError)
	cost_center = get_billing_cost_center(session_doc.service_branch, required=True)
	draft_invoice_name = None
	if is_draft_sales_invoice(session_doc.linked_invoice):
		draft_invoice_name = session_doc.linked_invoice
	elif session_doc.appointment and is_draft_sales_invoice(frappe.db.get_value(GROOMING_APPOINTMENT_DOCTYPE, session_doc.appointment, "linked_invoice")):
		draft_invoice_name = frappe.db.get_value(GROOMING_APPOINTMENT_DOCTYPE, session_doc.appointment, "linked_invoice")
	if draft_invoice_name:
		invoice = frappe.get_doc("Sales Invoice", draft_invoice_name)
		if invoice.customer and invoice.customer != session_doc.primary_owner:
			frappe.throw("Linked Invoice customer does not match the grooming owner.", frappe.ValidationError)
		invoice.customer = session_doc.primary_owner
		invoice.company = session_doc.get("company") or get_default_company()
		invoice.posting_date = getdate(session_doc.start_time or nowdate())
		invoice.due_date = getdate(session_doc.start_time or nowdate())
		invoice.remarks = f"Grooming billing for {session_doc.name}"
		if frappe.get_meta("Sales Invoice").has_field("branch"):
			invoice.branch = session_doc.service_branch
		if cost_center and frappe.get_meta("Sales Invoice").has_field("cost_center"):
			invoice.cost_center = cost_center
		return ensure_grooming_invoice_item(invoice, item_code, cost_center, default_rate), False
	if session_doc.linked_invoice and is_active_sales_invoice(session_doc.linked_invoice):
		return session_doc.linked_invoice, False
	if session_doc.appointment:
		appointment_invoice = frappe.db.get_value(GROOMING_APPOINTMENT_DOCTYPE, session_doc.appointment, "linked_invoice")
		if appointment_invoice and is_active_sales_invoice(appointment_invoice):
			return appointment_invoice, False
		if appointment_invoice and is_draft_sales_invoice(appointment_invoice):
			invoice = frappe.get_doc("Sales Invoice", appointment_invoice)
			return ensure_grooming_invoice_item(invoice, item_code, cost_center, default_rate), False
	item_payload = build_invoice_item(item_code, 1, None, default_rate, cost_center)
	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": session_doc.primary_owner,
			"company": session_doc.get("company") or get_default_company(),
			"posting_date": getdate(session_doc.start_time or nowdate()),
			"due_date": getdate(session_doc.start_time or nowdate()),
			"items": [item_payload],
			"remarks": f"Grooming billing for {session_doc.name}",
		}
	)
	if frappe.get_meta("Sales Invoice").has_field("branch"):
		invoice.branch = session_doc.service_branch
	if cost_center and frappe.get_meta("Sales Invoice").has_field("cost_center"):
		invoice.cost_center = cost_center
	invoice.insert(ignore_permissions=True)
	return invoice.name, True



def emit_grooming_appointment_event(doc, event: str, previous_status: str | None = None) -> dict:
	return emit_notification_event(
		event_key=event,
		reference_doctype=GROOMING_APPOINTMENT_DOCTYPE,
		reference_name=doc.name,
		payload={
			"appointment": doc.name,
			"patient": doc.patient,
			"primary_owner": doc.primary_owner,
			"service_branch": doc.service_branch,
			"grooming_service": doc.grooming_service,
			"groomer": doc.groomer,
			"scheduled_datetime": doc.scheduled_datetime,
			"previous_status": previous_status,
			"status": doc.status,
			"linked_invoice": doc.linked_invoice,
		},
	)


def use_billing_core_for_grooming() -> bool:
	try:
		from vetedge.services.billing_core import is_billing_sessions_enabled

		return is_billing_sessions_enabled()
	except Exception:
		return False


def emit_grooming_session_event(doc, event: str, previous_status: str | None = None) -> dict:
	return emit_notification_event(
		event_key=event,
		reference_doctype=GROOMING_SESSION_DOCTYPE,
		reference_name=doc.name,
		payload={
			"session": doc.name,
			"appointment": doc.appointment,
			"patient": doc.patient,
			"primary_owner": doc.primary_owner,
			"service_branch": doc.service_branch,
			"grooming_service": doc.grooming_service,
			"groomer": doc.groomer,
			"start_time": doc.start_time,
			"end_time": doc.end_time,
			"previous_status": previous_status,
			"status": doc.status,
			"linked_invoice": doc.linked_invoice,
		},
	)



def handle_grooming_appointment_after_insert(doc) -> None:
	emit_grooming_appointment_event(doc, "grooming_appointment_created")



def handle_grooming_appointment_on_update(doc) -> None:
	previous = doc.get_doc_before_save() if getattr(doc, "get_doc_before_save", None) else None
	if not previous or previous.status == doc.status:
		return
	if doc.status == "Confirmed":
		emit_grooming_appointment_event(doc, "grooming_appointment_confirmed", previous_status=previous.status)



def handle_grooming_session_on_update(doc) -> None:
	previous = doc.get_doc_before_save() if getattr(doc, "get_doc_before_save", None) else None
	if not previous or previous.status == doc.status:
		return
	if doc.status == "In Progress":
		emit_grooming_session_event(doc, "grooming_started", previous_status=previous.status)
	elif doc.status == "Completed":
		emit_grooming_session_event(doc, "grooming_completed", previous_status=previous.status)



@frappe.whitelist()
def transition_grooming_appointment_status(appointment: str, status: str) -> dict:
	require_internal_user()
	ensure_grooming_enabled()
	doc = frappe.get_doc(GROOMING_APPOINTMENT_DOCTYPE, appointment)
	can_manage_grooming_appointments(get_current_user(), doc, raise_exception=True)
	previous_status = doc.status
	doc.status = status
	doc.save()
	return {"name": doc.name, "status": doc.status, "previous_status": previous_status}



@frappe.whitelist()
def create_grooming_session_from_appointment(appointment: str, values: dict | str | None = None, create_invoice: int = 1) -> dict:
	require_internal_user()
	ensure_grooming_enabled()
	if not appointment:
		frappe.throw("Grooming Appointment is required.", frappe.ValidationError)
	appointment_doc = frappe.get_doc(GROOMING_APPOINTMENT_DOCTYPE, appointment)
	can_create_grooming_session(get_current_user(), appointment_doc, raise_exception=True)
	if appointment_doc.status in {"Completed", "Cancelled", "No Show"}:
		frappe.throw("Cannot start a grooming session from a completed, cancelled, or no-show appointment.", frappe.ValidationError)
	existing = frappe.get_all(
		GROOMING_SESSION_DOCTYPE,
		filters={"appointment": appointment_doc.name, "status": ["!=", "Cancelled"]},
		fields=["name", "status", "linked_invoice"],
		limit=1,
	)
	if existing:
		return {"name": existing[0].name, "status": existing[0].status, "linked_invoice": existing[0].linked_invoice}
	payload = frappe.parse_json(values or {})
	doc = frappe.get_doc(
		{
			"doctype": GROOMING_SESSION_DOCTYPE,
			"appointment": appointment_doc.name,
			"patient": appointment_doc.patient,
			"primary_owner": appointment_doc.primary_owner,
			"service_branch": appointment_doc.service_branch,
			"grooming_service": appointment_doc.grooming_service,
			"groomer": payload.get("groomer") or appointment_doc.groomer,
			"pre_grooming_notes": payload.get("pre_grooming_notes"),
			"post_grooming_notes": payload.get("post_grooming_notes"),
			"status": "Draft",
		}
	)
	doc.insert(ignore_permissions=True)
	if appointment_doc.status == "Confirmed":
		appointment_doc.status = "Checked In"
		appointment_doc.save(ignore_permissions=True)
	if int(create_invoice or 0):
		invoice_result = create_or_update_grooming_invoice(doc.name)
		if getattr(doc, "reload", None):
			doc.reload()
		return {"name": doc.name, "status": invoice_result.get("status") or doc.status, "linked_invoice": invoice_result.get("invoice")}
	return {"name": doc.name, "status": doc.status, "linked_invoice": doc.linked_invoice}



@frappe.whitelist()
def transition_grooming_session_status(session: str, status: str) -> dict:
	require_internal_user()
	ensure_grooming_enabled()
	doc = frappe.get_doc(GROOMING_SESSION_DOCTYPE, session)
	can_progress_grooming_session(get_current_user(), doc, raise_exception=True)
	previous_status = doc.status
	doc.status = status
	doc.save()
	if doc.appointment:
		appointment_status = {
			"In Progress": "In Progress",
			"Completed": "Completed",
			"Cancelled": "Cancelled",
		}.get(doc.status)
		if appointment_status:
			sync_grooming_appointment_status_for_session(doc.appointment, appointment_status)
	return {"name": doc.name, "status": doc.status, "previous_status": previous_status}



def sync_grooming_appointment_status_for_session(appointment: str, target_status: str) -> None:
	if not appointment or not target_status:
		return
	appointment_doc = frappe.get_doc(GROOMING_APPOINTMENT_DOCTYPE, appointment)
	if appointment_doc.status in {target_status, "Completed", "Cancelled", "No Show"}:
		return
	transition_paths = {
		"In Progress": ["Confirmed", "Checked In", "In Progress"],
		"Completed": ["Confirmed", "Checked In", "In Progress", "Completed"],
		"Cancelled": ["Cancelled"],
	}
	for next_status in transition_paths.get(target_status, []):
		if appointment_doc.status == next_status:
			continue
		allowed = VALID_APPOINTMENT_STATUS_TRANSITIONS.get(appointment_doc.status, set())
		if next_status not in allowed:
			continue
		appointment_doc.status = next_status
		appointment_doc.save(ignore_permissions=True)
		if appointment_doc.status == target_status:
			break



@frappe.whitelist()
def create_or_update_grooming_invoice(session: str) -> dict:
	require_internal_user()
	ensure_grooming_enabled()
	doc = frappe.get_doc(GROOMING_SESSION_DOCTYPE, session)
	can_manage_grooming_billing(get_current_user(), doc, raise_exception=True)
	if doc.status == "Cancelled":
		frappe.throw("Cancelled grooming sessions cannot be billed.", frappe.ValidationError)
	invoice_name, created = create_grooming_invoice(doc)
	set_grooming_invoice_links(doc, invoice_name)
	if doc.status not in {"Completed", "Cancelled", "In Progress"}:
		doc.status = get_grooming_session_workflow_status(doc)
	doc.save(ignore_permissions=True)
	if created and invoice_name:
		invoice_doc = frappe.get_doc("Sales Invoice", invoice_name)
		emit_notification_event(
			"grooming_invoice_created",
			GROOMING_SESSION_DOCTYPE,
			doc.name,
			{
				"session": doc.name,
				"appointment": doc.appointment,
				"patient": doc.patient,
				"primary_owner": doc.primary_owner,
				"service_branch": doc.service_branch,
				"grooming_service": doc.grooming_service,
				"invoice": invoice_name,
				"amount": invoice_doc.grand_total,
			},
		)
	return {"name": doc.name, "invoice": invoice_name, "status": doc.status}



def update_grooming_status_from_invoice(doc, method: str | None = None) -> None:
	for row in frappe.get_all(
		GROOMING_SESSION_DOCTYPE,
		filters={"linked_invoice": doc.name},
		fields=["name"],
	):
		sync_grooming_session_workflow_status(row.name)



def update_grooming_status_from_payment_entry(doc, method: str | None = None) -> None:
	for reference in doc.get("references") or []:
		if reference.reference_doctype != "Sales Invoice" or not reference.reference_name:
			continue
		invoice = frappe.get_doc("Sales Invoice", reference.reference_name)
		update_grooming_status_from_invoice(invoice, method)



def cint_bool(value) -> bool:
	return bool(int(value or 0))
