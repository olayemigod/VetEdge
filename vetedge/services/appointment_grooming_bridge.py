from __future__ import annotations

import frappe
from frappe.utils import cint, get_datetime, now_datetime

from vetedge.services.appointment_flow import ensure_appointments_enabled
from vetedge.services.consultation_flow import (
	get_document_title,
	get_user_full_name,
	validate_practitioner_branch_access,
)
from vetedge.services.grooming import (
	GROOMING_SESSION_SYSTEM_FIELDS,
	enforce_terminal_grooming_read_only,
	ensure_grooming_enabled,
	get_grooming_session_workflow_status,
	set_grooming_session_title,
	validate_grooming_session_status,
	validate_service_branch,
)
from vetedge.services.permissions import (
	GROOMER_ROLES,
	can_access_branch_data,
	can_create_grooming_session,
	get_current_user,
	get_user_roles,
)
from vetedge.services.portal_access import require_internal_user

GROOMING_APPOINTMENT_TYPE = "Grooming"
GROOMING_APPOINTMENT_STATUSES = {
	"Scheduled",
	"Confirmed",
	"Checked In",
	"In Service",
	"Completed",
	"Rescheduled",
	"Cancelled",
	"No Show",
}
GROOMING_APPOINTMENT_TRANSITIONS = {
	"Scheduled": {"Confirmed", "Rescheduled", "Cancelled", "No Show"},
	"Confirmed": {"Checked In", "In Service", "Rescheduled", "Cancelled", "No Show"},
	"Checked In": {"In Service", "Cancelled"},
	"In Service": {"Completed", "Cancelled"},
	"Rescheduled": {"Scheduled", "Confirmed", "Cancelled", "No Show"},
	"Completed": set(),
	"Cancelled": set(),
	"No Show": set(),
}


def is_grooming_veterinary_appointment(doc) -> bool:
	return bool(doc and doc.get("appointment_type") == GROOMING_APPOINTMENT_TYPE)


def validate_grooming_veterinary_appointment(doc) -> None:
	"""Validate Grooming scheduling without forcing a veterinary doctor.

	Veterinary Appointment remains the scheduling truth. Pet Grooming Session remains
	the service-execution and billing truth. Legacy Pet Grooming Appointment records
	remain supported separately and are not rewritten by this bridge.
	"""
	ensure_appointments_enabled()
	ensure_grooming_enabled()
	_validate_status(doc)
	_resolve_context(doc)
	_validate_datetime(doc)
	_validate_groomer_slot(doc)
	_set_title(doc)


def _validate_status(doc) -> None:
	if not doc.status:
		doc.status = "Scheduled"
	if doc.status not in GROOMING_APPOINTMENT_STATUSES:
		frappe.throw(f"Invalid Grooming appointment status: {doc.status}", frappe.ValidationError)
	previous = doc.get_doc_before_save() if getattr(doc, "get_doc_before_save", None) else None
	if not previous or previous.status == doc.status:
		return
	if previous.status in {"Completed", "Cancelled", "No Show"}:
		frappe.throw(
			f"Grooming appointment status cannot be changed after it is {previous.status}.",
			frappe.ValidationError,
		)
	allowed = GROOMING_APPOINTMENT_TRANSITIONS.get(previous.status, set())
	if doc.status not in allowed:
		frappe.throw(
			f"Grooming appointment status cannot move from {previous.status} to {doc.status}.",
			frappe.ValidationError,
		)


def _resolve_context(doc) -> None:
	if not doc.patient:
		frappe.throw("Patient is required for a Grooming appointment.", frappe.ValidationError)
	patient = frappe.db.get_value(
		"Veterinary Patient",
		doc.patient,
		["primary_owner", "default_branch", "status"],
		as_dict=True,
	)
	if not patient or patient.get("status") == "Deceased":
		frappe.throw("A valid active Veterinary Patient is required.", frappe.ValidationError)
	doc.primary_owner = patient.primary_owner
	if not doc.branch:
		doc.branch = patient.default_branch
	if not doc.primary_owner:
		frappe.throw("Patient must have a Primary Owner before Grooming can be scheduled.", frappe.ValidationError)
	if not doc.branch:
		frappe.throw("Branch is required for a Grooming appointment.", frappe.ValidationError)
	can_access_branch_data(get_current_user(), doc.branch, raise_exception=True)

	if not doc.grooming_service:
		frappe.throw("Grooming Service is required for a Grooming appointment.", frappe.ValidationError)
	service = frappe.db.get_value(
		"Pet Grooming Service",
		doc.grooming_service,
		["is_active", "service_name"],
		as_dict=True,
	)
	if not service:
		frappe.throw("Select a valid Pet Grooming Service.", frappe.ValidationError)
	if not cint(service.get("is_active")):
		frappe.throw(f"Grooming Service {doc.grooming_service} is inactive.", frappe.ValidationError)

	if not doc.groomer:
		frappe.throw("Groomer is required for a Grooming appointment.", frappe.ValidationError)
	if not (get_user_roles(doc.groomer) & GROOMER_ROLES):
		frappe.throw("Selected Groomer must have a VetEdge Groomer or administrative role.", frappe.ValidationError)
	validate_practitioner_branch_access(doc.groomer, doc.branch)
	doc.groomer_name = get_user_full_name(doc.groomer)

	# Grooming is not a consultation and must not inherit a doctor accidentally.
	doc.practitioner = None
	doc.practitioner_name = None
	doc.linked_consultation = None
	if not doc.created_from:
		doc.created_from = "Manual"


def _validate_datetime(doc) -> None:
	if not doc.appointment_datetime:
		frappe.throw("Appointment Date/Time is required.", frappe.ValidationError)
	try:
		get_datetime(doc.appointment_datetime)
	except Exception:
		frappe.throw("Appointment Date/Time must be a valid datetime.", frappe.ValidationError)


def _validate_groomer_slot(doc) -> None:
	if not doc.groomer or not doc.appointment_datetime or doc.status in {"Cancelled", "No Show"}:
		return
	filters = {
		"appointment_type": GROOMING_APPOINTMENT_TYPE,
		"groomer": doc.groomer,
		"appointment_datetime": doc.appointment_datetime,
		"status": ["not in", ["Cancelled", "No Show"]],
	}
	if getattr(doc, "name", None):
		filters["name"] = ["!=", doc.name]
	if frappe.get_all("Veterinary Appointment", filters=filters, pluck="name", limit=1):
		frappe.throw("Groomer already has an appointment at this exact date and time.", frappe.ValidationError)


def _set_title(doc) -> None:
	patient_title = get_document_title("Veterinary Patient", doc.patient) or doc.patient
	service_title = get_document_title("Pet Grooming Service", doc.grooming_service) or doc.grooming_service
	parts = [patient_title, "Grooming", service_title]
	if doc.appointment_datetime:
		parts.append(str(get_datetime(doc.appointment_datetime).strftime("%Y-%m-%d %H:%M")))
	if doc.groomer_name:
		parts.append(doc.groomer_name)
	if doc.branch:
		parts.append(doc.branch)
	doc.appointment_title = " - ".join(part for part in parts if part)


def populate_session_from_veterinary_appointment(session) -> None:
	appointment_name = session.get("veterinary_appointment")
	if not appointment_name:
		return
	appointment = frappe.get_doc("Veterinary Appointment", appointment_name)
	if not is_grooming_veterinary_appointment(appointment):
		frappe.throw("Pet Grooming Session must reference a Grooming Veterinary Appointment.", frappe.ValidationError)
	if appointment.status in {"Completed", "Cancelled", "No Show"}:
		frappe.throw(f"Cannot create or update a Grooming Session from a {appointment.status} appointment.", frappe.ValidationError)
	session.patient = appointment.patient
	session.primary_owner = appointment.primary_owner
	session.service_branch = appointment.branch
	session.grooming_service = appointment.grooming_service
	if not session.groomer:
		session.groomer = appointment.groomer


def validate_veterinary_appointment_grooming_session(session) -> None:
	"""Use existing Grooming workflow rules while accepting Veterinary Appointment as the schedule source."""
	ensure_grooming_enabled()
	previous = session.get_doc_before_save() if getattr(session, "get_doc_before_save", None) else None
	if not session.status:
		session.status = "Draft"
	validate_grooming_session_status(session, previous)
	populate_session_from_veterinary_appointment(session)
	session.status = get_grooming_session_workflow_status(session)
	if session.status in {"In Progress", "Completed"} and not session.start_time:
		session.start_time = now_datetime()
	if session.status == "Completed" and not session.end_time:
		session.end_time = now_datetime()
	if session.start_time:
		get_datetime(session.start_time)
	if session.end_time:
		end_time = get_datetime(session.end_time)
		if session.start_time and end_time < get_datetime(session.start_time):
			frappe.throw("End Time cannot be earlier than Start Time.", frappe.ValidationError)
	if session.status == "Completed" and not session.groomer:
		frappe.throw("Groomer is required before completing a grooming session.", frappe.ValidationError)
	validate_service_branch(session.service_branch, practitioner=session.groomer)
	set_grooming_session_title(session)
	enforce_terminal_grooming_read_only(
		session,
		previous,
		GROOMING_SESSION_SYSTEM_FIELDS | {"veterinary_appointment"},
		"Pet Grooming Session",
	)


@frappe.whitelist()
def create_grooming_session_from_veterinary_appointment(appointment: str) -> dict:
	require_internal_user()
	from vetedge.services.platform_access import require_vetedge_platform_access

	require_vetedge_platform_access(
		action="create_grooming_session_from_veterinary_appointment",
		reference_doctype="Veterinary Appointment",
		reference_name=appointment,
	)
	appointment_doc = frappe.get_doc("Veterinary Appointment", appointment)
	appointment_doc.check_permission("write")
	if not is_grooming_veterinary_appointment(appointment_doc):
		frappe.throw("Only Grooming Veterinary Appointments can create Grooming Sessions.", frappe.ValidationError)
	if appointment_doc.status not in {"Confirmed", "Checked In", "In Service"}:
		frappe.throw("Grooming appointment must be Confirmed or Checked In before creating its session.", frappe.ValidationError)
	can_access_branch_data(get_current_user(), appointment_doc.branch, raise_exception=True)
	can_create_grooming_session(get_current_user(), appointment_doc, raise_exception=True)

	existing = frappe.get_all(
		"Pet Grooming Session",
		filters={"veterinary_appointment": appointment_doc.name},
		fields=["name", "status"],
		order_by="creation desc",
		limit=1,
	)
	if existing:
		return {"name": existing[0].name, "status": existing[0].status, "created": False}

	session = frappe.get_doc(
		{
			"doctype": "Pet Grooming Session",
			"veterinary_appointment": appointment_doc.name,
			"patient": appointment_doc.patient,
			"primary_owner": appointment_doc.primary_owner,
			"service_branch": appointment_doc.branch,
			"grooming_service": appointment_doc.grooming_service,
			"groomer": appointment_doc.groomer,
			"status": "Draft",
		}
	)
	session.insert()
	return {"name": session.name, "status": session.status, "created": True}


def sync_veterinary_appointment_from_grooming_session(session) -> None:
	appointment_name = session.get("veterinary_appointment")
	if not appointment_name or not frappe.db.exists("Veterinary Appointment", appointment_name):
		return
	appointment = frappe.get_doc("Veterinary Appointment", appointment_name)
	if not is_grooming_veterinary_appointment(appointment):
		return
	target = {
		"In Progress": "In Service",
		"Completed": "Completed",
		"Cancelled": "Cancelled",
	}.get(session.status)
	if not target or appointment.status == target:
		return
	appointment.status = target
	appointment.save()
