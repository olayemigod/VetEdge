from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr


CONSULTATION_APPOINTMENT_TYPES = {"Consultation", "Follow Up"}
PRACTITIONER_REQUIRED_APPOINTMENT_TYPES = {"Consultation", "Follow Up", "Vaccination"}
KNOWN_APPOINTMENT_TYPES = {
	"Consultation",
	"Follow Up",
	"Vaccination",
	"Grooming",
	"Boarding",
	"Other",
}
PRE_SERVICE_STATUSES = {"Awaiting Registration", "Owner Requested"}


def appointment_type(doc) -> str:
	"""Return the effective type without rewriting historical blank records."""
	return cstr(doc.get("appointment_type") or "").strip() or "Consultation"


def _previous(doc):
	getter = getattr(doc, "get_doc_before_save", None)
	return getter() if getter else None


def _is_new_or_type_changed(doc, target_type: str) -> bool:
	previous = _previous(doc)
	if previous is None:
		return True
	return appointment_type(previous) != target_type


def get_originating_consultation(reference: str | None):
	if not reference:
		return None
	if not frappe.db.exists("Veterinary Consultation", reference):
		frappe.throw(_("Originating Consultation must be a valid Veterinary Consultation."), frappe.ValidationError)
	return frappe.db.get_value(
		"Veterinary Consultation",
		reference,
		[
			"name",
			"patient",
			"primary_owner",
			"service_branch",
			"consulting_practitioner",
			"consulting_practitioner_name",
			"consultation_type",
			"status",
			"consultation_datetime",
		],
		as_dict=True,
	)


def resolve_appointment_vaccine(doc) -> str | None:
	vaccine = cstr(doc.get("vaccine") or "").strip()
	if vaccine:
		return vaccine
	if doc.get("source_doctype") == "Veterinary Vaccination Record" and doc.get("source_name"):
		if frappe.db.exists("Veterinary Vaccination Record", doc.source_name):
			return frappe.db.get_value("Veterinary Vaccination Record", doc.source_name, "vaccine")
	return None


def resolve_appointment_consultation_type(doc) -> str | None:
	consultation_type = cstr(doc.get("consultation_type") or "").strip()
	if consultation_type:
		return consultation_type
	if appointment_type(doc) == "Follow Up" and doc.get("follow_up_reference"):
		return frappe.db.get_value("Veterinary Consultation", doc.follow_up_reference, "consultation_type")
	return None


def prepare_appointment_service_context(doc) -> None:
	"""Fill safe service defaults before the standard Appointment validator runs."""
	service_type = appointment_type(doc)
	if doc.get("appointment_type") and service_type not in KNOWN_APPOINTMENT_TYPES:
		frappe.throw(_("Appointment Type is invalid."), frappe.ValidationError)

	if service_type == "Follow Up":
		doc.is_follow_up = 1
		origin = get_originating_consultation(doc.get("follow_up_reference")) if doc.get("follow_up_reference") else None
		if origin:
			if not doc.get("patient"):
				doc.patient = origin.patient
			if not doc.get("primary_owner"):
				doc.primary_owner = origin.primary_owner
			if not doc.get("branch"):
				doc.branch = origin.service_branch
			if not doc.get("practitioner"):
				doc.practitioner = origin.consulting_practitioner
			if not doc.get("consultation_type"):
				doc.consultation_type = origin.consultation_type
	elif doc.get("appointment_type"):
		doc.is_follow_up = 0
		doc.follow_up_reference = None

	if service_type in CONSULTATION_APPOINTMENT_TYPES:
		if not doc.get("consultation_type"):
			doc.consultation_type = resolve_appointment_consultation_type(doc) or "General Consultation"
	elif doc.get("appointment_type"):
		doc.consultation_type = None

	if service_type == "Vaccination":
		if not doc.get("vaccine"):
			doc.vaccine = resolve_appointment_vaccine(doc)
	elif doc.get("appointment_type"):
		doc.vaccine = None


def validate_appointment_service_context(doc) -> None:
	"""Enforce type-specific correctness without relying on conditional UI fields."""
	service_type = appointment_type(doc)

	if (
		service_type in PRACTITIONER_REQUIRED_APPOINTMENT_TYPES
		and doc.get("status") not in PRE_SERVICE_STATUSES
		and not doc.get("practitioner")
	):
		frappe.throw(_("Veterinary Practitioner is required for {0} appointments.").format(service_type), frappe.ValidationError)

	if service_type in CONSULTATION_APPOINTMENT_TYPES:
		consultation_type = cstr(doc.get("consultation_type") or "").strip()
		if not consultation_type:
			frappe.throw(_("Consultation Type is required for {0} appointments.").format(service_type), frappe.ValidationError)
		values = frappe.db.get_value("Consultation Type", consultation_type, ["name", "disabled"], as_dict=True)
		if not values or cint(values.disabled):
			frappe.throw(_("Select an active Consultation Type."), frappe.ValidationError)

	if service_type == "Follow Up":
		reference = cstr(doc.get("follow_up_reference") or "").strip()
		if not reference:
			if _is_new_or_type_changed(doc, "Follow Up"):
				frappe.throw(_("Originating Consultation is required for a new Follow Up appointment."), frappe.ValidationError)
		else:
			origin = get_originating_consultation(reference)
			if origin.patient and doc.get("patient") and origin.patient != doc.patient:
				frappe.throw(_("Originating Consultation must belong to the selected patient."), frappe.ValidationError)
			if origin.status == "Cancelled":
				frappe.throw(_("A cancelled Consultation cannot be used as the origin of a Follow Up appointment."), frappe.ValidationError)

	if service_type == "Vaccination":
		vaccine = resolve_appointment_vaccine(doc)
		if not vaccine:
			if _is_new_or_type_changed(doc, "Vaccination"):
				frappe.throw(_("Vaccine is required for a new Vaccination appointment."), frappe.ValidationError)
			return
		values = frappe.db.get_value("Veterinary Vaccine", vaccine, ["name", "is_active", "species"], as_dict=True)
		if not values or not cint(values.is_active):
			frappe.throw(_("Select an active Veterinary Vaccine."), frappe.ValidationError)
		patient_species = frappe.db.get_value("Veterinary Patient", doc.get("patient"), "species") if doc.get("patient") else None
		if values.species and patient_species and values.species != patient_species:
			frappe.throw(
				_("Vaccine {0} is configured for Species {1}, not {2}.").format(vaccine, values.species, patient_species),
				frappe.ValidationError,
			)
		doc.vaccine = vaccine

	if service_type == "Other" and not cstr(doc.get("notes") or "").strip() and _is_new_or_type_changed(doc, "Other"):
		frappe.throw(_("Reason / Notes is required for a new Other appointment."), frappe.ValidationError)
