from __future__ import annotations

from datetime import datetime

import frappe
from frappe.utils import add_days, cstr, get_datetime, getdate, now, now_datetime

from vetedge.services.consultation_flow import (
	get_document_title,
	get_user_full_name,
	validate_practitioner_branch_access,
	validate_user_branch_access,
)
from vetedge.services.feature_flags import is_enabled
from vetedge.services.notifications import emit_notification_event
from vetedge.services.payment_gate import assert_consultation_can_proceed
from vetedge.services.permissions import (
	ELEVATED_ROLES,
	FRONT_DESK_ROLES,
	ROLE_BRANCH_MANAGER,
	can_access_consultation,
	user_has_any_role,
	validate_doctor_user,
)
from vetedge.services.portal_access import require_internal_user
from vetedge.services.registration_billing import validate_registration_payment_before_first_consultation


APPOINTMENT_STATUSES = {
	"Awaiting Registration",
	"Owner Requested",
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
	"Awaiting Registration": {"Owner Requested", "Cancelled"},
	"Owner Requested": {"Scheduled", "Cancelled"},
	"Scheduled": {"Confirmed", "Rescheduled", "Cancelled", "No Show"},
	"Confirmed": {"Checked In", "In Consultation", "Rescheduled", "Cancelled", "No Show"},
	"Checked In": {"In Consultation"},
	"In Consultation": {"Completed"},
	"Rescheduled": {"Scheduled", "Confirmed", "Cancelled", "No Show"},
	"Completed": set(),
	"Cancelled": set(),
	"No Show": set(),
}

ACTIVE_QUEUE_STATUSES = (
	"Awaiting Registration",
	"Owner Requested",
	"Scheduled",
	"Confirmed",
	"Checked In",
	"In Consultation",
	"Rescheduled",
)


def validate_appointment(doc) -> None:
	ensure_appointments_enabled()
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
		if doc.status == "Awaiting Registration" and doc.guest_booking_request:
			doc.created_from = doc.created_from or "Guest"
			doc.appointment_title = make_guest_appointment_title(doc)
			return

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

	validate_doctor_user(doc.practitioner)
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

	if doc.created_from == "Guest" and doc.status == "Awaiting Registration":
		return

	if doc.created_from == "Portal" and doc.status == "Owner Requested":
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
	if not doc.patient and doc.status == "Awaiting Registration":
		doc.appointment_title = make_guest_appointment_title(doc)
		return

	patient_title = get_document_title("Veterinary Patient", doc.patient) or doc.patient
	parts = [patient_title]
	if doc.appointment_datetime:
		parts.append(str(get_datetime(doc.appointment_datetime).strftime("%Y-%m-%d %H:%M")))
	if doc.practitioner_name:
		parts.append(doc.practitioner_name)
	if doc.branch:
		parts.append(doc.branch)

	doc.appointment_title = " - ".join(part for part in parts if part)


def make_guest_appointment_title(doc) -> str:
	guest_label = "Guest Registration"
	if doc.guest_booking_request:
		guest_name, pet_name = frappe.db.get_value(
			"Veterinary Guest Booking Request",
			doc.guest_booking_request,
			["guest_name", "pet_name"],
		) or (None, None)
		guest_label = " / ".join(part for part in (guest_name, pet_name) if part) or guest_label

	parts = [guest_label]
	if doc.appointment_datetime:
		parts.append(str(get_datetime(doc.appointment_datetime).strftime("%Y-%m-%d %H:%M")))
	if doc.branch:
		parts.append(doc.branch)

	return " - ".join(part for part in parts if part)


@frappe.whitelist()
def create_follow_up_from_consultation(
	consultation: str,
	appointment_datetime: str | datetime,
	notes: str | None = None,
) -> dict:
	require_internal_user()
	ensure_appointments_enabled()
	can_access_consultation(frappe.session.user, consultation, raise_exception=True)
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
	appointment.insert(ignore_permissions=True)
	emit_appointment_event(appointment, "appointment_created", previous_status=None)

	consultation_meta = frappe.get_meta("Veterinary Consultation")
	if consultation_meta.has_field("follow_up_appointment"):
		frappe.db.set_value("Veterinary Consultation", consultation_doc.name, "follow_up_appointment", appointment.name)
	elif consultation_meta.has_field("linked_appointment"):
		frappe.db.set_value("Veterinary Consultation", consultation_doc.name, "linked_appointment", appointment.name)

	return {
		"name": appointment.name,
		"appointment_title": appointment.appointment_title,
	}


@frappe.whitelist()
def create_consultation_from_appointment(appointment: str) -> dict:
	require_internal_user()
	ensure_appointments_enabled()
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
	assert_consultation_can_proceed(consultation, "In Progress")
	consultation.insert()

	appointment_doc.linked_consultation = consultation.name
	previous_status = appointment_doc.status
	appointment_doc.status = "In Consultation"
	appointment_doc.save()
	emit_appointment_status_notification(appointment_doc, previous_status, appointment_doc.status)

	return {
		"name": consultation.name,
		"consultation_title": consultation.consultation_title,
	}


@frappe.whitelist()
def transition_appointment_status(appointment: str, status: str) -> dict:
	require_internal_user()
	ensure_appointments_enabled()
	appointment_doc = frappe.get_doc("Veterinary Appointment", appointment)
	previous_status = appointment_doc.status
	appointment_doc.status = status
	appointment_doc.save()
	emit_appointment_status_notification(appointment_doc, previous_status, appointment_doc.status)

	return {
		"name": appointment_doc.name,
		"status": appointment_doc.status,
	}


def emit_appointment_status_notification(appointment_doc, previous_status: str | None, status: str) -> dict | None:
	event = get_appointment_status_event(status)
	if not event:
		return None

	return emit_appointment_event(appointment_doc, event, previous_status=previous_status)


def emit_appointment_event(appointment_doc, event: str, previous_status: str | None = None) -> dict:
	return emit_notification_event(
		event_key=event,
		reference_doctype="Veterinary Appointment",
		reference_name=appointment_doc.name,
		payload={
			"appointment": appointment_doc.name,
			"patient": appointment_doc.get("patient"),
			"primary_owner": appointment_doc.get("primary_owner"),
			"branch": appointment_doc.get("branch"),
			"practitioner": appointment_doc.get("practitioner"),
			"appointment_datetime": appointment_doc.get("appointment_datetime"),
			"appointment_type": appointment_doc.get("appointment_type"),
			"previous_status": previous_status,
			"status": appointment_doc.get("status"),
			"created_from": appointment_doc.get("created_from"),
		},
	)


def get_appointment_status_event(status: str) -> str | None:
	return {
		"Scheduled": "appointment_scheduled",
		"Confirmed": "appointment_confirmed",
		"Checked In": "appointment_checked_in",
		"In Consultation": "appointment_started",
		"Completed": "appointment_completed",
		"Rescheduled": "appointment_rescheduled",
		"Cancelled": "appointment_cancelled",
		"No Show": "appointment_no_show",
	}.get(status)


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

	validate_registration_payment_before_first_consultation(appointment_doc.patient)


@frappe.whitelist()
def get_appointment_queue(
	branch: str | None = None,
	practitioner: str | None = None,
	status: str | None = None,
	reference_date: str | None = None,
) -> dict[str, list[dict]]:
	require_internal_user()
	ensure_appointments_enabled()
	today = getdate(reference_date or now_datetime())
	tomorrow = add_days(today, 1)
	future_start = add_days(today, 2)

	return {
		"today": get_appointments_between(today, today, branch=branch, practitioner=practitioner, status=status),
		"tomorrow": get_appointments_between(
			tomorrow,
			tomorrow,
			branch=branch,
			practitioner=practitioner,
			status=status,
		),
		"future": get_future_appointments(future_start, branch=branch, practitioner=practitioner, status=status),
	}


def get_appointments_between(
	start_date,
	end_date,
	branch: str | None = None,
	practitioner: str | None = None,
	status: str | None = None,
) -> list[dict]:
	filters = {
		"appointment_datetime": [
			"between",
			[f"{getdate(start_date)} 00:00:00", f"{getdate(end_date)} 23:59:59"],
		],
	}
	add_optional_queue_filters(filters, branch=branch, practitioner=practitioner, status=status)
	return fetch_queue_rows(filters)


def ensure_appointments_enabled() -> None:
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return

	if is_enabled("appointments"):
		return

	frappe.throw("Appointments are not enabled in Veterinary Settings.", frappe.ValidationError)


def get_future_appointments(
	start_date,
	branch: str | None = None,
	practitioner: str | None = None,
	status: str | None = None,
) -> list[dict]:
	filters = {
		"appointment_datetime": [">=", f"{getdate(start_date)} 00:00:00"],
	}
	add_optional_queue_filters(filters, branch=branch, practitioner=practitioner, status=status)
	return fetch_queue_rows(filters)


def add_optional_queue_filters(
	filters: dict,
	branch: str | None = None,
	practitioner: str | None = None,
	status: str | None = None,
) -> None:
	if status:
		if status not in APPOINTMENT_STATUSES:
			frappe.throw(f"Invalid appointment status: {status}", frappe.ValidationError)
		filters["status"] = status
	else:
		filters["status"] = ["in", ACTIVE_QUEUE_STATUSES]

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


GENERATED_APPOINTMENT_MUTABLE_STATUSES = {
	"Awaiting Registration",
	"Owner Requested",
	"Scheduled",
	"Confirmed",
	"Rescheduled",
}
MISSED_APPOINTMENT_STATUSES = {
	"Awaiting Registration",
	"Owner Requested",
	"Scheduled",
}
MISSED_RESOLVED_STATUSES = APPOINTMENT_STATUSES - MISSED_APPOINTMENT_STATUSES
MISSED_APPOINTMENT_ACTIVE_STATUSES = {"Open", "Contacted", "Reopened"}
MISSED_APPOINTMENT_MANAGER_ROLES = {*ELEVATED_ROLES, ROLE_BRANCH_MANAGER, "VetEdge Branch Manager"}
MISSED_APPOINTMENT_ACTION_ROLES = {
	*ELEVATED_ROLES,
	*FRONT_DESK_ROLES,
	ROLE_BRANCH_MANAGER,
	"VetEdge Branch Manager",
	"VetEdge Doctor",
}
DEFAULT_GENERATED_APPOINTMENT_TIME = "09:00:00"


def sync_follow_up_appointment_from_consultation(doc) -> str | None:
	if not frappe.db.exists("DocType", "Veterinary Appointment"):
		return None

	appointment_date = doc.get("follow_up_date")
	return sync_generated_appointment(
		source_doc=doc,
		source_field="follow_up_date",
		appointment_date=appointment_date,
		appointment_type="Follow Up",
		created_from="Consultation",
		generated_from="Consultation Follow-up",
		reason="Follow-up Consultation",
		backlink_field="follow_up_appointment",
		is_follow_up=1,
		follow_up_reference=doc.name,
	)


def sync_next_vaccination_appointment_from_record(doc) -> str | None:
	if not frappe.db.exists("DocType", "Veterinary Appointment"):
		return None

	appointment_date = doc.get("next_vaccination_date") or doc.get("next_due_date")
	return sync_generated_appointment(
		source_doc=doc,
		source_field="next_due_date",
		appointment_date=appointment_date,
		appointment_type="Vaccination",
		created_from="Vaccination",
		generated_from="Vaccination Next Due",
		reason=_vaccination_appointment_reason(doc),
		backlink_field="next_vaccination_appointment",
		is_follow_up=0,
		follow_up_reference=None,
	)


def sync_generated_appointment(
	source_doc,
	source_field: str,
	appointment_date,
	appointment_type: str,
	created_from: str,
	generated_from: str,
	reason: str,
	backlink_field: str | None = None,
	is_follow_up: int = 0,
	follow_up_reference: str | None = None,
) -> str | None:
	existing_name = _find_generated_appointment(source_doc.doctype, source_doc.name, source_field, backlink_field, source_doc)
	if not appointment_date:
		_cancel_generated_appointment_if_safe(existing_name, source_doc, backlink_field)
		return None

	appointment_datetime = normalize_generated_appointment_datetime(appointment_date)
	values = _build_generated_appointment_values(
		source_doc=source_doc,
		appointment_datetime=appointment_datetime,
		appointment_type=appointment_type,
		created_from=created_from,
		generated_from=generated_from,
		reason=reason,
		source_field=source_field,
		is_follow_up=is_follow_up,
		follow_up_reference=follow_up_reference,
	)

	if existing_name:
		appointment = frappe.get_doc("Veterinary Appointment", existing_name)
		if appointment.status in GENERATED_APPOINTMENT_MUTABLE_STATUSES:
			for fieldname, value in values.items():
				if getattr(appointment, fieldname, None) != value:
					setattr(appointment, fieldname, value)
			appointment.save()
		_update_source_backlink(source_doc, backlink_field, appointment.name)
		return appointment.name

	appointment = frappe.get_doc({"doctype": "Veterinary Appointment", **values})
	appointment.insert()
	_update_source_backlink(source_doc, backlink_field, appointment.name)
	return appointment.name


def normalize_generated_appointment_datetime(value):
	text = cstr(value).strip()
	if len(text) <= 10:
		return f"{getdate(value)} {DEFAULT_GENERATED_APPOINTMENT_TIME}"
	return get_datetime(value)


def _build_generated_appointment_values(
	source_doc,
	appointment_datetime,
	appointment_type: str,
	created_from: str,
	generated_from: str,
	reason: str,
	source_field: str,
	is_follow_up: int,
	follow_up_reference: str | None,
) -> dict:
	return {
		"patient": source_doc.get("patient"),
		"primary_owner": source_doc.get("primary_owner"),
		"branch": source_doc.get("service_branch") or source_doc.get("branch"),
		"practitioner": _appointment_practitioner_from_source(source_doc),
		"appointment_datetime": appointment_datetime,
		"status": "Scheduled",
		"appointment_type": appointment_type,
		"created_from": created_from,
		"source_doctype": source_doc.doctype,
		"source_name": source_doc.name,
		"source_field": source_field,
		"generated_from": generated_from,
		"is_follow_up": is_follow_up,
		"follow_up_reference": follow_up_reference,
		"notes": reason,
	}


def _appointment_practitioner_from_source(source_doc) -> str | None:
	practitioner = source_doc.get("consulting_practitioner") or source_doc.get("practitioner")
	if practitioner:
		return practitioner

	administered_by = source_doc.get("administered_by")
	if not administered_by:
		return None
	try:
		validate_doctor_user(administered_by)
	except Exception:
		return None
	return administered_by


def _find_generated_appointment(source_doctype: str, source_name: str, source_field: str, backlink_field: str | None = None, source_doc=None) -> str | None:
	if backlink_field and source_doc and source_doc.get(backlink_field):
		if frappe.db.exists("Veterinary Appointment", source_doc.get(backlink_field)):
			return source_doc.get(backlink_field)

	meta = frappe.get_meta("Veterinary Appointment")
	if meta.has_field("source_doctype") and meta.has_field("source_name") and meta.has_field("source_field"):
		matches = frappe.get_all(
			"Veterinary Appointment",
			filters={
				"source_doctype": source_doctype,
				"source_name": source_name,
				"source_field": source_field,
			},
			pluck="name",
			limit=1,
		)
		if matches:
			return matches[0]

	if source_doctype == "Veterinary Consultation":
		matches = frappe.get_all(
			"Veterinary Appointment",
			filters={"follow_up_reference": source_name, "is_follow_up": 1},
			pluck="name",
			limit=1,
		)
		if matches:
			return matches[0]

	return None


def _cancel_generated_appointment_if_safe(appointment_name: str | None, source_doc, backlink_field: str | None = None) -> None:
	if not appointment_name:
		_update_source_backlink(source_doc, backlink_field, None)
		return
	appointment = frappe.get_doc("Veterinary Appointment", appointment_name)
	if appointment.status in GENERATED_APPOINTMENT_MUTABLE_STATUSES:
		appointment.status = "Cancelled"
		appointment.save()
		_update_source_backlink(source_doc, backlink_field, None)


def _update_source_backlink(source_doc, fieldname: str | None, appointment_name: str | None) -> None:
	if not fieldname or not source_doc.get("name"):
		return
	meta = frappe.get_meta(source_doc.doctype)
	if not meta.has_field(fieldname):
		return
	if source_doc.get(fieldname) == appointment_name:
		return
	frappe.db.set_value(source_doc.doctype, source_doc.name, fieldname, appointment_name, update_modified=False)
	setattr(source_doc, fieldname, appointment_name)


def _vaccination_appointment_reason(doc) -> str:
	parts = ["Vaccination"]
	if doc.get("vaccine"):
		parts.append(cstr(doc.get("vaccine")))
	return " - ".join(parts)


@frappe.whitelist()
def sync_missed_appointments(branch: str | None = None) -> dict:
	ensure_appointments_enabled()
	if not frappe.db.exists("DocType", "Veterinary Missed Appointment"):
		return {"created": 0, "updated": 0, "resolved": 0}

	reference_datetime = now_datetime()
	filters = {
		"appointment_datetime": ["<", reference_datetime],
		"status": ["in", sorted(MISSED_APPOINTMENT_STATUSES)],
	}
	if branch:
		filters["branch"] = branch

	created = updated = 0
	for row in frappe.get_all("Veterinary Appointment", filters=filters, fields=_missed_appointment_source_fields()):
		result = upsert_missed_appointment(row)
		if result == "created":
			created += 1
		elif result == "updated":
			updated += 1

	resolved = resolve_stale_missed_appointments(branch=branch)
	return {"created": created, "updated": updated, "resolved": resolved}


def sync_missed_appointment_from_source(appointment_doc) -> str | None:
	if not frappe.db.exists("DocType", "Veterinary Missed Appointment"):
		return None
	row = _appointment_doc_to_missed_source_row(appointment_doc)
	if is_missed_appointment_row(row):
		return upsert_missed_appointment(row)
	return resolve_missed_appointment_for_source(appointment_doc.name, appointment_doc.status)


def upsert_missed_appointment(row) -> str:
	appointment_name = row.get("name")
	existing_name = frappe.db.exists("Veterinary Missed Appointment", {"appointment": appointment_name})
	values = {
		"appointment": appointment_name,
		"appointment_datetime": row.get("appointment_datetime"),
		"patient": row.get("patient"),
		"primary_owner": row.get("primary_owner"),
		"branch": row.get("branch"),
		"practitioner": row.get("practitioner"),
		"original_status": row.get("status"),
		"status": "Open",
		"resolved": 0,
		"resolution_status": None,
		"resolved_on": None,
		"resolved_by": None,
	}
	if existing_name:
		missed = frappe.get_doc("Veterinary Missed Appointment", existing_name)
		if getattr(missed, "resolved", 0):
			return "unchanged"
		changed = False
		for fieldname, value in values.items():
			if getattr(missed, fieldname, None) != value:
				setattr(missed, fieldname, value)
				changed = True
		if changed:
			missed.save(ignore_permissions=True)
			return "updated"
		return "unchanged"

	missed = frappe.get_doc({"doctype": "Veterinary Missed Appointment", **values})
	missed.insert(ignore_permissions=True)
	return "created"


def resolve_stale_missed_appointments(branch: str | None = None) -> int:
	filters = {"status": ["in", sorted(MISSED_APPOINTMENT_ACTIVE_STATUSES)], "resolved": 0}
	if branch:
		filters["branch"] = branch
	resolved = 0
	for missed in frappe.get_all("Veterinary Missed Appointment", filters=filters, fields=["name", "appointment"]):
		if not missed.get("appointment") or not frappe.db.exists("Veterinary Appointment", missed.get("appointment")):
			continue
		appointment = frappe.get_doc("Veterinary Appointment", missed.get("appointment"))
		if not is_missed_appointment_row(_appointment_doc_to_missed_source_row(appointment)):
			if resolve_missed_appointment_for_source(appointment.name, appointment.status):
				resolved += 1
	return resolved


def resolve_missed_appointment_for_source(appointment_name: str, resolution_status: str | None = None) -> str | None:
	existing_name = frappe.db.exists("Veterinary Missed Appointment", {"appointment": appointment_name})
	if not existing_name:
		return None
	missed = frappe.get_doc("Veterinary Missed Appointment", existing_name)
	if missed.resolved:
		return None
	missed.status = "Resolved"
	missed.resolved = 1
	missed.resolution_status = resolution_status
	missed.resolved_on = now()
	missed.resolved_by = frappe.session.user
	missed.save(ignore_permissions=True)
	return "resolved"


@frappe.whitelist()
def reschedule_missed_appointment(
	missed_appointment: str,
	new_date: str,
	new_time: str | None = None,
	note: str | None = None,
) -> dict:
	missed, appointment = _get_missed_action_docs(missed_appointment)
	_validate_missed_appointment_action(missed, appointment)
	if getattr(missed, "resolved", 0):
		return _missed_action_response(missed, appointment)

	if not new_date:
		frappe.throw("New appointment date is required.", frappe.ValidationError)

	new_datetime = _combine_missed_reschedule_datetime(new_date, new_time)
	if get_datetime(new_datetime) <= now_datetime():
		frappe.throw("Rescheduled appointment date/time must be in the future.", frappe.ValidationError)

	previous_status = appointment.status
	appointment.appointment_datetime = new_datetime
	appointment.status = _rescheduled_appointment_status(appointment.status)
	appointment.save()
	emit_appointment_status_notification(appointment, previous_status, appointment.status)

	missed = _apply_missed_resolution_db(
		missed.name,
		status="Rescheduled",
		resolution_status="Rescheduled",
		note=note,
	)
	_ensure_single_active_missed_record(missed)

	return _missed_action_response(missed, appointment)


@frappe.whitelist()
def cancel_missed_appointment(missed_appointment: str, note: str | None = None) -> dict:
	missed, appointment = _get_missed_action_docs(missed_appointment)
	_validate_missed_appointment_action(missed, appointment)
	if getattr(missed, "resolved", 0):
		return _missed_action_response(missed, appointment)

	previous_status = appointment.status
	appointment.status = "Cancelled"
	appointment.save()
	emit_appointment_status_notification(appointment, previous_status, appointment.status)

	missed = _apply_missed_resolution_db(
		missed.name,
		status="Cancelled",
		resolution_status="Cancelled",
		note=note,
	)
	_ensure_single_active_missed_record(missed)

	return _missed_action_response(missed, appointment)


@frappe.whitelist()
def mark_missed_appointment_contacted(missed_appointment: str, note: str | None = None) -> dict:
	missed, appointment = _get_missed_action_docs(missed_appointment)
	_validate_missed_appointment_action(missed, appointment)
	if getattr(missed, "resolved", 0):
		frappe.throw("Resolved missed appointments cannot be marked contacted.", frappe.ValidationError)
	_ensure_single_active_missed_record(missed)

	missed.status = "Contacted"
	missed.contacted = 1
	missed.contacted_on = now()
	missed.contacted_by = frappe.session.user
	missed.contact_note = note
	missed.save()

	return _missed_action_response(missed, appointment)


@frappe.whitelist()
def resolve_missed_appointment(missed_appointment: str, resolution_note: str | None = None) -> dict:
	missed, appointment = _get_missed_action_docs(missed_appointment)
	_validate_missed_appointment_action(missed, appointment)
	if getattr(missed, "resolved", 0):
		return _missed_action_response(missed, appointment)

	if (
		is_missed_appointment_row(_appointment_doc_to_missed_source_row(appointment))
		and not cstr(resolution_note).strip()
		and not _current_user_can_manage_missed_appointments()
	):
		frappe.throw(
			"Resolution note is required while the linked appointment is still missed-eligible.",
			frappe.PermissionError,
		)

	_apply_missed_resolution(
		missed,
		status="Resolved",
		resolution_status="Resolved",
		note=resolution_note,
	)
	_ensure_single_active_missed_record(missed)

	return _missed_action_response(missed, appointment)


@frappe.whitelist()
def reopen_missed_appointment(missed_appointment: str, note: str | None = None) -> dict:
	missed, appointment = _get_missed_action_docs(missed_appointment)
	_validate_missed_appointment_action(missed, appointment, manager_required=True)

	missed.status = "Reopened"
	missed.resolved = 0
	missed.resolved_on = None
	missed.resolved_by = None
	missed.resolution_status = "Reopened"
	missed.resolution_note = note
	missed.save()
	_ensure_single_active_missed_record(missed)

	return _missed_action_response(missed, appointment)


def _get_missed_action_docs(missed_appointment: str):
	require_internal_user()
	ensure_appointments_enabled()

	missed = frappe.get_doc("Veterinary Missed Appointment", missed_appointment)
	if not missed.appointment:
		frappe.throw("Missed appointment must be linked to a Veterinary Appointment.", frappe.ValidationError)

	appointment = frappe.get_doc("Veterinary Appointment", missed.appointment)
	if missed.branch and appointment.branch and missed.branch != appointment.branch:
		frappe.throw("Missed appointment branch does not match the linked appointment.", frappe.ValidationError)
	validate_user_branch_access(missed.branch or appointment.branch)
	return missed, appointment


def _validate_missed_appointment_action(missed, appointment, manager_required: bool = False) -> None:
	user = frappe.session.user
	roles = MISSED_APPOINTMENT_MANAGER_ROLES if manager_required else MISSED_APPOINTMENT_ACTION_ROLES
	if not user_has_any_role(user, roles):
		frappe.throw("Not permitted to act on this missed appointment.", frappe.PermissionError)

	if manager_required:
		return

	has_permission = getattr(appointment, "has_permission", None)
	if user_has_any_role(user, {"VetEdge Doctor"}) and has_permission and not has_permission("write"):
		frappe.throw("Not permitted to update the linked appointment.", frappe.PermissionError)


def _combine_missed_reschedule_datetime(new_date: str, new_time: str | None = None):
	if new_time:
		return get_datetime(f"{getdate(new_date)} {cstr(new_time).strip()}")
	return get_datetime(new_date)


def _rescheduled_appointment_status(status: str | None) -> str:
	if status == "Awaiting Registration":
		return "Awaiting Registration"
	return "Scheduled"


def _apply_missed_resolution(missed, status: str, resolution_status: str, note: str | None = None) -> None:
	missed.status = status
	missed.resolved = 1
	missed.resolution_status = resolution_status
	missed.resolution_note = note
	missed.resolved_on = now()
	missed.resolved_by = frappe.session.user
	missed.save()


def _apply_missed_resolution_db(missed_name: str, status: str, resolution_status: str, note: str | None = None):
	frappe.db.set_value(
		"Veterinary Missed Appointment",
		missed_name,
		{
			"status": status,
			"resolved": 1,
			"resolution_status": resolution_status,
			"resolution_note": note,
			"resolved_on": now(),
			"resolved_by": frappe.session.user,
		},
	)
	return frappe.get_doc("Veterinary Missed Appointment", missed_name)


def _current_user_can_manage_missed_appointments() -> bool:
	return user_has_any_role(frappe.session.user, MISSED_APPOINTMENT_MANAGER_ROLES)


def _ensure_single_active_missed_record(missed) -> None:
	active = frappe.get_all(
		"Veterinary Missed Appointment",
		filters={
			"appointment": missed.appointment,
			"resolved": 0,
			"name": ["!=", missed.name],
		},
		pluck="name",
	)
	if active:
		frappe.throw(
			"Another active missed appointment already exists for the linked appointment.",
			frappe.ValidationError,
		)


def _missed_action_response(missed, appointment) -> dict:
	return {
		"name": missed.name,
		"status": missed.status,
		"resolved": missed.resolved,
		"appointment": appointment.name,
		"appointment_status": appointment.status,
		"appointment_datetime": appointment.appointment_datetime,
	}


def is_missed_appointment_row(row, reference_datetime=None) -> bool:
	if cstr(row.get("status")) not in MISSED_APPOINTMENT_STATUSES:
		return False
	appointment_datetime = row.get("appointment_datetime")
	if not appointment_datetime:
		return False
	return get_datetime(appointment_datetime) < get_datetime(reference_datetime or now_datetime())


def _missed_appointment_source_fields() -> list[str]:
	return [
		"name",
		"appointment_datetime",
		"patient",
		"primary_owner",
		"branch",
		"practitioner",
		"status",
	]


def _appointment_doc_to_missed_source_row(appointment_doc) -> dict:
	return {fieldname: appointment_doc.get(fieldname) for fieldname in _missed_appointment_source_fields()}
