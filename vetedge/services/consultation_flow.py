from __future__ import annotations

from types import SimpleNamespace

import frappe
from frappe.utils import flt, getdate

from vetedge.services.dispensary import (
	sync_consultation_dispensary_state,
	validate_consultation_dispensary_requirements,
)
from vetedge.services.billing import (
	validate_consultation_invoice_before_progress,
	validate_consultation_payment_before_treatment,
)
from vetedge.services.feature_flags import is_enabled
from vetedge.services.notifications import emit_notification_event
from vetedge.services.payment_gate import assert_consultation_can_proceed
from vetedge.services.registration_billing import validate_registration_payment_before_first_consultation
from vetedge.services.permissions import (
	DOCTOR_ROLES,
	can_access_branch_data,
	can_access_consultation,
	validate_doctor_user,
	validate_consultation_clinical_permissions,
)
from vetedge.services.portal_access import require_internal_user
from vetedge.services.treatment_items import apply_planned_treatment_defaults


CONSULTATION_STATUSES = {
	"Draft",
	"In Progress",
	"Awaiting Payment",
	"Pending Dispensary",
	"Ready for Treatment",
	"Completed",
	"Cancelled",
}

VALID_CONSULTATION_STATUS_TRANSITIONS = {
	"Draft": {"In Progress", "Cancelled"},
	"In Progress": {"Awaiting Payment", "Pending Dispensary", "Ready for Treatment", "Completed", "Cancelled"},
	"Awaiting Payment": {"Pending Dispensary", "Ready for Treatment", "Completed", "Cancelled"},
	"Pending Dispensary": {"Ready for Treatment", "Completed", "Cancelled"},
	"Ready for Treatment": {"Completed", "Cancelled"},
	"Completed": set(),
	"Cancelled": set(),
}

CONSULTATION_READY_APPOINTMENT_STATUSES = (
	"Confirmed",
	"Checked In",
)

CONSULTATION_APPOINTMENT_STATUS_MAP = {
	"Completed": "Completed",
	"Cancelled": "Cancelled",
}

CONSULTATION_SCOPE_LOCKED_STATUSES = {
	"Ready for Treatment",
	"Completed",
	"Cancelled",
}


def validate_consultation(doc) -> None:
	ensure_consultations_enabled()
	validate_consultation_status(doc)
	validate_consultation_scope_lock(doc)
	normalize_consultation_appointment_links(doc)
	apply_linked_appointment_context(doc)
	resolve_consultation_context(doc)
	if consultation_requires_registration_payment_gate(doc):
		validate_registration_payment_before_first_consultation(doc.patient, current_consultation=getattr(doc, "name", None))
	validate_linked_appointment(doc)
	set_consultation_title(doc)
	validate_service_branch_access(doc)
	validate_consultation_children(doc)
	sync_consultation_dispensary_state(doc)
	validate_completion_requirements(doc)


def consultation_requires_registration_payment_gate(doc) -> bool:
	return (getattr(doc, "status", None) or "Draft") not in {"Draft", "Cancelled"}


def validate_consultation_status(doc) -> None:
	if not doc.status:
		doc.status = "Draft"

	if doc.status not in CONSULTATION_STATUSES:
		frappe.throw(f"Invalid consultation status: {doc.status}", frappe.ValidationError)

	previous = doc.get_doc_before_save() if getattr(doc, "get_doc_before_save", None) else None
	if previous and previous.status in {"Completed", "Cancelled"} and doc.status != previous.status:
		frappe.throw(
			f"Consultation status cannot be changed after it is {previous.status}.",
			frappe.ValidationError,
		)

	if previous and previous.status != doc.status:
		validate_consultation_status_transition(previous.status, doc.status)

	validate_paid_consultation_cancellation(doc, previous)


def validate_consultation_status_transition(current_status: str, target_status: str) -> None:
	allowed = VALID_CONSULTATION_STATUS_TRANSITIONS.get(current_status, set())
	if target_status not in allowed:
		frappe.throw(
			f"Consultation status cannot move from {current_status} to {target_status}.",
			frappe.ValidationError,
		)


def validate_paid_consultation_cancellation(doc, previous=None) -> None:
	if doc.status != "Cancelled":
		return

	previous_status = getattr(previous, "status", None) if previous else None
	if previous_status == "Cancelled":
		return

	if getattr(doc, "payment_status", None) == "Paid":
		frappe.throw(
			"Paid consultations cannot be cancelled. Start the appropriate refund or finance reversal flow first, then create a new consultation if needed.",
			frappe.ValidationError,
		)


def consultation_scope_is_locked(status: str | None) -> bool:
	return (status or "") in CONSULTATION_SCOPE_LOCKED_STATUSES


def validate_consultation_scope_lock(doc) -> None:
	previous = doc.get_doc_before_save() if getattr(doc, "get_doc_before_save", None) else None
	if not previous or not consultation_scope_is_locked(previous.status):
		return

	if _serialize_planned_treatments(doc) == _serialize_planned_treatments(previous):
		return

	frappe.throw(
		"Treatment items cannot be added or changed after the consultation is Ready for Treatment. "
		"Start a new consultation to capture additional treatment, lab, vaccine, or other clinical orders.",
		frappe.ValidationError,
	)


def validate_consultation_allows_new_clinical_entries(doc, entry_type: str = "clinical items") -> None:
	if not consultation_scope_is_locked(getattr(doc, "status", None)):
		return

	frappe.throw(
		f"This consultation is already {doc.status}. No new {entry_type} can be added. "
		"Start a new consultation for additional treatment, lab, vaccine, or other clinical orders.",
		frappe.ValidationError,
	)


@frappe.whitelist()
def transition_consultation_status(consultation: str, status: str) -> dict:
	require_internal_user()
	ensure_consultations_enabled()
	doc = frappe.get_doc("Veterinary Consultation", consultation)
	can_access_consultation(frappe.session.user, consultation, raise_exception=True)
	validate_consultation_status_transition(doc.status, status)
	assert_consultation_can_proceed(doc, status)
	previous = SimpleNamespace(status=doc.status)
	doc.status = status
	validate_paid_consultation_cancellation(doc, previous)
	doc.save()

	return {
		"name": doc.name,
		"status": doc.status,
	}


def ensure_consultations_enabled() -> None:
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return

	if is_enabled("consultations"):
		return

	frappe.throw("Consultations are not enabled in Veterinary Settings.", frappe.ValidationError)


def resolve_consultation_context(doc) -> None:
	if not doc.patient:
		frappe.throw("Patient is required for Veterinary Consultation.", frappe.ValidationError)

	patient = frappe.db.get_value(
		"Veterinary Patient",
		doc.patient,
		["primary_owner", "default_branch"],
		as_dict=True,
	)
	if not patient:
		frappe.throw("Veterinary Consultation must reference a valid Veterinary Patient.", frappe.ValidationError)

	if not patient.primary_owner:
		frappe.throw("Patient must have a Primary Owner before consultation.", frappe.ValidationError)

	doc.primary_owner = patient.primary_owner

	if not doc.service_branch and patient.default_branch:
		doc.service_branch = patient.default_branch

	if not doc.service_branch:
		frappe.throw("Service Branch is required for Veterinary Consultation.", frappe.ValidationError)

	if not doc.consultation_datetime:
		doc.consultation_datetime = frappe.utils.now_datetime()

	if not doc.company:
		doc.company = get_default_company()

	if not doc.consulting_practitioner:
		doc.consulting_practitioner = get_default_consulting_practitioner()

	validate_doctor_user(doc.consulting_practitioner, label="Consulting Practitioner")
	doc.consulting_practitioner_name = get_user_full_name(doc.consulting_practitioner)
	set_daily_consultation_number(doc)


def apply_linked_appointment_context(doc) -> None:
	if not doc.linked_appointment:
		return

	appointment = get_linked_appointment_data(doc.linked_appointment)
	if not appointment:
		return

	if appointment.branch and not doc.service_branch:
		doc.service_branch = appointment.branch
	if appointment.practitioner and not doc.consulting_practitioner:
		doc.consulting_practitioner = appointment.practitioner
	if appointment.notes and not doc.presenting_complaint:
		doc.presenting_complaint = appointment.notes


def normalize_consultation_appointment_links(doc) -> None:
	if not doc.linked_appointment or not getattr(doc, "name", None):
		return

	appointment = get_linked_appointment_data(doc.linked_appointment)
	if not appointment:
		return

	if appointment.follow_up_reference != doc.name:
		return

	if frappe.get_meta("Veterinary Consultation").has_field("follow_up_appointment"):
		doc.follow_up_appointment = doc.linked_appointment
		doc.linked_appointment = None


def validate_linked_appointment(doc) -> None:
	if not doc.linked_appointment:
		return

	appointment = get_linked_appointment_data(doc.linked_appointment)
	if not appointment:
		frappe.throw("Linked Appointment must be a valid Veterinary Appointment.", frappe.ValidationError)

	if appointment.patient != doc.patient:
		frappe.throw("Linked Appointment must belong to the selected Veterinary Patient.", frappe.ValidationError)

	if appointment.linked_consultation and appointment.linked_consultation != doc.name:
		frappe.throw(
			"Linked Appointment already has another Veterinary Consultation.",
			frappe.ValidationError,
		)

	if appointment.status in CONSULTATION_READY_APPOINTMENT_STATUSES:
		return

	if appointment.status == "In Consultation" and appointment.linked_consultation == doc.name:
		return

	frappe.throw(
		"Linked Appointment must be Confirmed or Checked In before consultation can start.",
		frappe.ValidationError,
	)


def claim_linked_appointment_for_consultation(doc) -> None:
	if not doc.linked_appointment:
		return

	appointment = get_linked_appointment_data(doc.linked_appointment)
	if not appointment:
		frappe.throw("Linked Appointment must be a valid Veterinary Appointment.", frappe.ValidationError)

	if appointment.linked_consultation and appointment.linked_consultation != doc.name:
		frappe.throw(
			"Linked Appointment already has another Veterinary Consultation.",
			frappe.ValidationError,
		)

	if appointment.status not in CONSULTATION_READY_APPOINTMENT_STATUSES:
		if appointment.status == "In Consultation" and appointment.linked_consultation == doc.name:
			return
		frappe.throw(
			"Linked Appointment must be Confirmed or Checked In before consultation can start.",
			frappe.ValidationError,
		)

	frappe.db.set_value(
		"Veterinary Appointment",
		appointment.name,
		{
			"linked_consultation": doc.name,
			"status": "In Consultation",
		},
		update_modified=False,
	)


def sync_service_appointment_status_from_consultation(doc) -> None:
	if not doc.linked_appointment or doc.status not in CONSULTATION_APPOINTMENT_STATUS_MAP:
		return

	appointment = get_linked_appointment_data(doc.linked_appointment)
	if not appointment:
		return

	if appointment.linked_consultation and appointment.linked_consultation != doc.name:
		frappe.throw(
			"Service Appointment is linked to another Veterinary Consultation.",
			frappe.ValidationError,
		)

	target_status = CONSULTATION_APPOINTMENT_STATUS_MAP[doc.status]
	if appointment.status == target_status:
		return

	if target_status == "Cancelled" and appointment.status == "Completed":
		return

	frappe.db.set_value(
		"Veterinary Appointment",
		appointment.name,
		"status",
		target_status,
		update_modified=False,
	)
	emit_service_appointment_status_event(appointment, target_status)


def emit_service_appointment_status_event(appointment, status: str) -> dict | None:
	event = {
		"Completed": "appointment_completed",
		"Cancelled": "appointment_cancelled",
	}.get(status)
	if not event:
		return None

	return emit_notification_event(
		event_key=event,
		reference_doctype="Veterinary Appointment",
		reference_name=appointment.name,
		payload={
			"appointment": appointment.name,
			"patient": appointment.patient,
			"branch": appointment.branch,
			"practitioner": appointment.practitioner,
			"previous_status": appointment.status,
			"status": status,
			"linked_consultation": appointment.linked_consultation,
		},
	)


def get_linked_appointment_data(appointment: str):
	return frappe.db.get_value(
		"Veterinary Appointment",
		appointment,
		["name", "patient", "status", "branch", "practitioner", "notes", "linked_consultation", "follow_up_reference"],
		as_dict=True,
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_pending_appointments_for_patient(doctype, txt, searchfield, start, page_len, filters):
	require_internal_user()
	patient = (filters or {}).get("patient")
	if not patient:
		return []

	search = f"%{txt}%"
	return frappe.db.sql(
		"""
		SELECT
			name,
			appointment_title
		FROM `tabVeterinary Appointment`
		WHERE patient = %(patient)s
			AND status IN %(statuses)s
			AND (linked_consultation IS NULL OR linked_consultation = '')
			AND (
				name LIKE %(search)s
				OR appointment_title LIKE %(search)s
				OR appointment_datetime LIKE %(search)s
			)
		ORDER BY appointment_datetime ASC
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"patient": patient,
			"statuses": CONSULTATION_READY_APPOINTMENT_STATUSES,
			"search": search,
			"start": start,
			"page_len": page_len,
		},
	)


def set_consultation_title(doc) -> None:
	patient_title = get_document_title("Veterinary Patient", doc.patient) or doc.patient
	parts = [patient_title]
	if doc.consultation_datetime:
		parts.append(str(getdate(doc.consultation_datetime)))
	if doc.daily_consultation_number:
		parts.append(f"Consultation {doc.daily_consultation_number}")
	if doc.consulting_practitioner_name:
		parts.append(doc.consulting_practitioner_name)
	if doc.service_branch:
		parts.append(doc.service_branch)

	doc.consultation_title = " - ".join(part for part in parts if part)


def set_daily_consultation_number(doc) -> None:
	if doc.daily_consultation_number or not doc.patient or not doc.consultation_datetime:
		return

	doc.daily_consultation_number = get_next_daily_consultation_number(
		doc.patient,
		doc.consultation_datetime,
		getattr(doc, "name", None),
	)


def get_next_daily_consultation_number(patient: str, consultation_datetime, current_name: str | None = None) -> int:
	day = getdate(consultation_datetime)
	filters = {
		"patient": patient,
		"consultation_datetime": ["between", [f"{day} 00:00:00", f"{day} 23:59:59"]],
	}
	if current_name:
		filters["name"] = ["!=", current_name]

	rows = frappe.get_all(
		"Veterinary Consultation",
		filters=filters,
		fields=["daily_consultation_number"],
	)
	numbers = [int(row.daily_consultation_number or 0) for row in rows]
	return (max(numbers) if numbers else 0) + 1


def get_document_title(doctype: str, name: str | None) -> str | None:
	if not name:
		return None

	meta = frappe.get_meta(doctype)
	title_field = meta.get_title_field()
	if title_field and title_field != "name":
		return frappe.db.get_value(doctype, name, title_field)

	return name


def get_user_full_name(user: str | None) -> str | None:
	if not user:
		return None

	full_name = frappe.db.get_value("User", user, "full_name")
	return full_name or user


def get_default_consulting_practitioner(user: str | None = None) -> str | None:
	user = user or getattr(frappe.session, "user", None)
	if not user or user == "Guest":
		return None
	get_roles = getattr(frappe, "get_roles", None)
	if get_roles and (set(get_roles(user)) & DOCTOR_ROLES):
		return user
	return None


def validate_service_branch_access(doc) -> None:
	if not doc.service_branch:
		return

	validate_user_branch_access(doc.service_branch)
	validate_practitioner_branch_access(doc.consulting_practitioner, doc.service_branch)


def validate_user_branch_access(service_branch: str) -> None:
	can_access_branch_data(frappe.session.user, service_branch, raise_exception=True)


def validate_practitioner_branch_access(practitioner: str | None, service_branch: str) -> None:
	if not practitioner or not frappe.db.exists("DocType", "Branch Practitioner Assignment"):
		return

	base_filters = {"practitioner": practitioner}
	if frappe.get_meta("Branch Practitioner Assignment").has_field("disabled"):
		base_filters["disabled"] = ["!=", 1]

	if not frappe.get_all(
		"Branch Practitioner Assignment",
		filters=base_filters,
		limit=1,
	):
		return

	filters = dict(base_filters, branch=service_branch)

	assignments = frappe.get_all(
		"Branch Practitioner Assignment",
		filters=filters,
		limit=1,
	)
	if not assignments:
		frappe.throw(
			f"Practitioner {practitioner} is not assigned to Service Branch {service_branch}.",
			frappe.PermissionError,
		)


def validate_consultation_children(doc) -> None:
	validate_consultation_clinical_permissions(doc)
	for row in doc.get("symptoms") or []:
		validate_enabled_link("Veterinary Symptom", row.symptom, "Symptom")

	for row in doc.get("diagnoses") or []:
		validate_enabled_link("Veterinary Diagnosis", row.diagnosis, "Diagnosis")

	for row in doc.get("planned_treatments") or []:
		apply_planned_treatment_defaults(row)
		if flt(row.qty) <= 0:
			frappe.throw("Planned Treatment Qty must be greater than zero.", frappe.ValidationError)
		if row.get("rate") not in (None, "") and flt(row.rate) < 0:
			frappe.throw("Planned Treatment Rate cannot be negative.", frappe.ValidationError)
		row.amount = flt(row.qty) * flt(row.get("rate"))
		validate_enabled_item(row.item)
		validate_enabled_link("Veterinary Service Type", row.service_type, "Service Type", required=False)
		validate_enabled_link("Veterinary Treatment Type", row.treatment_type, "Treatment Type", required=False)


def _serialize_planned_treatments(doc) -> list[tuple]:
	return [
		(
			row.get("name"),
			row.get("item"),
			flt(row.get("qty")),
			row.get("uom"),
			flt(row.get("rate")) if row.get("rate") not in (None, "") else None,
			row.get("service_type"),
			row.get("treatment_type"),
		)
		for row in doc.get("planned_treatments") or []
	]


def validate_enabled_link(doctype: str, name: str | None, label: str, required: bool = True) -> None:
	if not name:
		if required:
			frappe.throw(f"{label} is required.", frappe.ValidationError)
		return

	if not frappe.db.exists(doctype, name):
		frappe.throw(f"{label} must reference a valid {doctype}.", frappe.ValidationError)

	if frappe.get_meta(doctype).has_field("disabled") and frappe.db.get_value(doctype, name, "disabled"):
		frappe.throw(f"{label} cannot reference a disabled {doctype}.", frappe.ValidationError)


def validate_enabled_item(item: str | None) -> None:
	if not item:
		frappe.throw("Planned Treatment Item is required.", frappe.ValidationError)

	item_data = frappe.db.get_value("Item", item, ["disabled"], as_dict=True)
	if not item_data:
		frappe.throw("Planned Treatment Item must reference a valid Item.", frappe.ValidationError)

	if item_data.disabled:
		frappe.throw("Planned Treatment Item cannot reference a disabled Item.", frappe.ValidationError)


def validate_completion_requirements(doc) -> None:
	assert_consultation_can_proceed(doc, doc.status)
	validate_consultation_dispensary_requirements(doc)

	if doc.status != "Completed":
		return

	if is_vitals_required_before_completion() and not has_vitals_for_consultation(doc.name):
		frappe.throw(
			"Veterinary Vital Signs are required before completing this consultation.",
			frappe.ValidationError,
		)


def is_vitals_required_before_completion() -> bool:
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return False

	settings = frappe.get_single("Veterinary Settings")
	meta = frappe.get_meta("Veterinary Settings")
	if not meta.has_field("require_vitals_before_completion"):
		return False

	return bool(settings.enable_vetedge and settings.enable_vitals and settings.require_vitals_before_completion)


def has_vitals_for_consultation(consultation: str | None) -> bool:
	if not consultation:
		return False

	return bool(frappe.db.exists("Veterinary Vital Signs", {"consultation": consultation}))


def get_default_company() -> str | None:
	try:
		from erpnext import get_default_company as erpnext_get_default_company

		return erpnext_get_default_company() or get_first_company()
	except Exception:
		return get_first_company()


def get_first_company() -> str | None:
	companies = frappe.get_all("Company", pluck="name", limit=1)
	return companies[0] if companies else None
