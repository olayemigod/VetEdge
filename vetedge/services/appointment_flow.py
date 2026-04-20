from __future__ import annotations

from datetime import datetime

import frappe
from frappe.utils import add_days, get_datetime, getdate, now_datetime

from vetedge.services.consultation_flow import (
	get_document_title,
	get_user_full_name,
	validate_practitioner_branch_access,
	validate_user_branch_access,
)


APPOINTMENT_STATUSES = {
	"Scheduled",
	"Confirmed",
	"Checked In",
	"In Consultation",
	"Completed",
	"Rescheduled",
	"Cancelled",
	"No Show",
}

VALID_STATUS_TRANSITIONS = {
	"Scheduled": {"Confirmed", "Rescheduled", "Cancelled", "No Show"},
	"Confirmed": {"Checked In", "In Consultation", "Rescheduled", "Cancelled", "No Show"},
	"Checked In": {"In Consultation"},
	"In Consultation": {"Completed"},
	"Rescheduled": {"Scheduled", "Confirmed", "Cancelled", "No Show"},
	"Completed": set(),
	"Cancelled": set(),
	"No Show": set(),
}

ACTIVE_QUEUE_STATUSES = ("Scheduled", "Confirmed", "Checked In", "In Consultation", "Rescheduled")


def validate_appointment(doc) -> None:
	normalize_consultation_links(doc)
	validate_status(doc)
	resolve_appointment_context(doc)
	validate_appointment_datetime(doc)
	validate_branch_access(doc)
	validate_follow_up_reference(doc)
	validate_linked_consultation(doc)
	validate_duplicate_practitioner_slot(doc)
	set_appointment_title(doc)


def normalize_consultation_links(doc) -> None:
	if doc.follow_up_reference:
		doc.is_follow_up = 1

	if doc.is_follow_up and doc.follow_up_reference and doc.linked_consultation == doc.follow_up_reference:
		doc.linked_consultation = None


def validate_status(doc) -> None:
	if not doc.status:
		doc.status = "Scheduled"

	if doc.status not in APPOINTMENT_STATUSES:
		frappe.throw(f"Invalid appointment status: {doc.status}", frappe.ValidationError)

	previous = doc.get_doc_before_save() if getattr(doc, "get_doc_before_save", None) else None
	if not previous or previous.status == doc.status:
		return

	if previous.status in {"Completed", "Cancelled", "No Show"}:
		frappe.throw(
			f"Appointment status cannot be changed after it is {previous.status}.",
			frappe.ValidationError,
		)

	allowed = VALID_STATUS_TRANSITIONS.get(previous.status, set())
	if doc.status not in allowed:
		frappe.throw(
			f"Appointment status cannot move from {previous.status} to {doc.status}.",
			frappe.ValidationError,
		)


def resolve_appointment_context(doc) -> None:
	if not doc.patient:
		frappe.throw("Patient is required for Veterinary Appointment.", frappe.ValidationError)

	patient = frappe.db.get_value(
		"Veterinary Patient",
		doc.patient,
		["primary_owner", "default_branch"],
		as_dict=True,
	)
	if not patient:
		frappe.throw("Veterinary Appointment must reference a valid Veterinary Patient.", frappe.ValidationError)

	if not patient.primary_owner:
		frappe.throw("Patient must have a Primary Owner before appointment booking.", frappe.ValidationError)

	doc.primary_owner = patient.primary_owner

	if not doc.branch and patient.default_branch:
		doc.branch = patient.default_branch

	if not doc.branch:
		frappe.throw("Branch is required for Veterinary Appointment.", frappe.ValidationError)

	if not doc.created_from:
		doc.created_from = "Manual"

	doc.practitioner_name = get_user_full_name(doc.practitioner)


def validate_appointment_datetime(doc) -> None:
	if not doc.appointment_datetime:
		frappe.throw("Appointment Date/Time is required.", frappe.ValidationError)

	try:
		get_datetime(doc.appointment_datetime)
	except Exception:
		frappe.throw("Appointment Date/Time must be a valid datetime.", frappe.ValidationError)


def validate_branch_access(doc) -> None:
	if not doc.branch:
		return

	validate_user_branch_access(doc.branch)
	validate_practitioner_branch_access(doc.practitioner, doc.branch)


def validate_follow_up_reference(doc) -> None:
	if not (doc.is_follow_up or doc.follow_up_reference):
		return

	if not doc.follow_up_reference:
		frappe.throw("Follow-up Reference is required for follow-up appointments.", frappe.ValidationError)

	if not frappe.db.exists("Veterinary Consultation", doc.follow_up_reference):
		frappe.throw("Follow-up Reference must be a valid Veterinary Consultation.", frappe.ValidationError)


def validate_linked_consultation(doc) -> None:
	if not doc.linked_consultation:
		return

	if not frappe.db.exists("Veterinary Consultation", doc.linked_consultation):
		frappe.throw("Linked Consultation must be a valid Veterinary Consultation.", frappe.ValidationError)

	if doc.follow_up_reference and doc.linked_consultation == doc.follow_up_reference:
		frappe.throw(
			"Linked Consultation must be the consultation created from this appointment, not the originating follow-up consultation.",
			frappe.ValidationError,
		)


def validate_duplicate_practitioner_slot(doc) -> None:
	if not doc.practitioner or not doc.appointment_datetime:
		return

	if doc.status in {"Cancelled", "No Show"}:
		return

	filters = {
		"practitioner": doc.practitioner,
		"appointment_datetime": doc.appointment_datetime,
		"status": ["not in", ["Cancelled", "No Show"]],
	}
	if getattr(doc, "name", None):
		filters["name"] = ["!=", doc.name]

	existing = frappe.get_all("Veterinary Appointment", filters=filters, pluck="name", limit=1)
	if existing:
		frappe.throw(
			"Practitioner already has an appointment at this exact date and time.",
			frappe.ValidationError,
		)


def set_appointment_title(doc) -> None:
	patient_title = get_document_title("Veterinary Patient", doc.patient) or doc.patient
	parts = [patient_title]
	if doc.appointment_datetime:
		parts.append(str(get_datetime(doc.appointment_datetime).strftime("%Y-%m-%d %H:%M")))
	if doc.practitioner_name:
		parts.append(doc.practitioner_name)
	if doc.branch:
		parts.append(doc.branch)

	doc.appointment_title = " - ".join(part for part in parts if part)


@frappe.whitelist()
def create_follow_up_from_consultation(
	consultation: str,
	appointment_datetime: str | datetime,
	notes: str | None = None,
) -> dict:
	consultation_doc = frappe.get_doc("Veterinary Consultation", consultation)
	if not consultation_doc.patient:
		frappe.throw("Consultation must have a patient before creating a follow-up appointment.")

	appointment = frappe.get_doc(
		{
			"doctype": "Veterinary Appointment",
			"patient": consultation_doc.patient,
			"primary_owner": consultation_doc.primary_owner,
			"branch": consultation_doc.service_branch,
			"practitioner": consultation_doc.consulting_practitioner,
			"appointment_datetime": appointment_datetime,
			"status": "Scheduled",
			"appointment_type": "Follow Up",
			"created_from": "Consultation",
			"is_follow_up": 1,
			"follow_up_reference": consultation_doc.name,
			"notes": notes,
		}
	)
	appointment.insert()

	if frappe.get_meta("Veterinary Consultation").has_field("linked_appointment"):
		frappe.db.set_value("Veterinary Consultation", consultation_doc.name, "linked_appointment", appointment.name)

	return {
		"name": appointment.name,
		"appointment_title": appointment.appointment_title,
	}


@frappe.whitelist()
def create_consultation_from_appointment(appointment: str) -> dict:
	appointment_doc = frappe.get_doc("Veterinary Appointment", appointment)
	normalize_consultation_links(appointment_doc)
	validate_start_consultation_from_appointment(appointment_doc)

	consultation = frappe.get_doc(
		{
			"doctype": "Veterinary Consultation",
			"patient": appointment_doc.patient,
			"primary_owner": appointment_doc.primary_owner,
			"service_branch": appointment_doc.branch,
			"consulting_practitioner": appointment_doc.practitioner,
			"consultation_datetime": now_datetime(),
			"status": "In Progress",
			"linked_appointment": appointment_doc.name,
			"presenting_complaint": appointment_doc.notes,
		}
	)
	consultation.insert()

	appointment_doc.linked_consultation = consultation.name
	appointment_doc.status = "In Consultation"
	appointment_doc.save()

	return {
		"name": consultation.name,
		"consultation_title": consultation.consultation_title,
	}


@frappe.whitelist()
def transition_appointment_status(appointment: str, status: str) -> dict:
	appointment_doc = frappe.get_doc("Veterinary Appointment", appointment)
	appointment_doc.status = status
	appointment_doc.save()

	return {
		"name": appointment_doc.name,
		"status": appointment_doc.status,
	}


def validate_start_consultation_from_appointment(appointment_doc) -> None:
	if appointment_doc.linked_consultation:
		frappe.throw(
			"Appointment already has a linked Veterinary Consultation.",
			frappe.ValidationError,
		)

	if appointment_doc.status not in {"Confirmed", "Checked In"}:
		frappe.throw(
			"Appointment must be Confirmed or Checked In before starting consultation.",
			frappe.ValidationError,
		)

	if not appointment_doc.patient:
		frappe.throw("Appointment must have a patient before starting consultation.", frappe.ValidationError)

	if not appointment_doc.branch:
		frappe.throw("Appointment must have a branch before starting consultation.", frappe.ValidationError)


@frappe.whitelist()
def get_appointment_queue(
	branch: str | None = None,
	practitioner: str | None = None,
	reference_date: str | None = None,
) -> dict[str, list[dict]]:
	today = getdate(reference_date or now_datetime())
	tomorrow = add_days(today, 1)
	future_start = add_days(today, 2)

	return {
		"today": get_appointments_between(today, today, branch=branch, practitioner=practitioner),
		"tomorrow": get_appointments_between(tomorrow, tomorrow, branch=branch, practitioner=practitioner),
		"future": get_future_appointments(future_start, branch=branch, practitioner=practitioner),
	}


def get_appointments_between(
	start_date,
	end_date,
	branch: str | None = None,
	practitioner: str | None = None,
) -> list[dict]:
	filters = {
		"appointment_datetime": [
			"between",
			[f"{getdate(start_date)} 00:00:00", f"{getdate(end_date)} 23:59:59"],
		],
		"status": ["in", ACTIVE_QUEUE_STATUSES],
	}
	add_optional_queue_filters(filters, branch=branch, practitioner=practitioner)
	return fetch_queue_rows(filters)


def get_future_appointments(
	start_date,
	branch: str | None = None,
	practitioner: str | None = None,
) -> list[dict]:
	filters = {
		"appointment_datetime": [">=", f"{getdate(start_date)} 00:00:00"],
		"status": ["in", ACTIVE_QUEUE_STATUSES],
	}
	add_optional_queue_filters(filters, branch=branch, practitioner=practitioner)
	return fetch_queue_rows(filters)


def add_optional_queue_filters(filters: dict, branch: str | None = None, practitioner: str | None = None) -> None:
	if branch:
		filters["branch"] = branch
	if practitioner:
		filters["practitioner"] = practitioner


def fetch_queue_rows(filters: dict) -> list[dict]:
	return frappe.get_all(
		"Veterinary Appointment",
		filters=filters,
		fields=[
			"name",
			"appointment_title",
			"patient",
			"primary_owner",
			"practitioner",
			"practitioner_name",
			"branch",
			"appointment_datetime",
			"status",
			"appointment_type",
		],
		order_by="appointment_datetime asc",
	)
