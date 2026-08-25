from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cstr


PRACTITIONER_REQUIRED_DOCTYPES = {
	"Veterinary Consultation": "consulting_practitioner",
	"Veterinary Appointment": "practitioner",
	"Veterinary Lab Order": "requested_by",
	"Veterinary Vaccination Record": "administered_by",
	"Pet Grooming Appointment": "groomer",
	"Pet Grooming Session": "groomer",
}

APPOINTMENT_PRACTITIONER_OPTIONAL_STATUSES = {
	"Awaiting Registration",
	"Owner Requested",
}


def enforce_practitioner_integrity(doc, method: str | None = None) -> None:
	fieldname = PRACTITIONER_REQUIRED_DOCTYPES.get(getattr(doc, "doctype", None))
	if not fieldname:
		return

	_populate_responsible_user(doc, fieldname)

	if _can_skip_practitioner_requirement(doc):
		return

	_require_non_empty_user(doc, fieldname)


def _populate_responsible_user(doc, fieldname: str) -> None:
	if cstr(doc.get(fieldname) or "").strip():
		return

	if doc.doctype == "Veterinary Consultation":
		from vetedge.services.consultation_flow import get_default_consulting_practitioner

		if doc.get("linked_appointment"):
			practitioner = frappe.db.get_value(
				"Veterinary Appointment",
				doc.linked_appointment,
				"practitioner",
			)
			if practitioner:
				doc.set(fieldname, practitioner)
				return

		default_practitioner = get_default_consulting_practitioner()
		if default_practitioner:
			doc.set(fieldname, default_practitioner)
		return

	if doc.doctype == "Veterinary Appointment":
		source_consultation = doc.get("follow_up_reference") or doc.get("linked_consultation")
		if source_consultation:
			practitioner = frappe.db.get_value(
				"Veterinary Consultation",
				source_consultation,
				"consulting_practitioner",
			)
			if practitioner:
				doc.set(fieldname, practitioner)
		return

	if doc.doctype == "Veterinary Lab Order":
		current_user = _current_user()
		if current_user:
			doc.set(fieldname, current_user)
		return

	if doc.doctype == "Veterinary Vaccination Record":
		if doc.get("linked_consultation"):
			practitioner = frappe.db.get_value(
				"Veterinary Consultation",
				doc.linked_consultation,
				"consulting_practitioner",
			)
			if practitioner:
				doc.set(fieldname, practitioner)
				return

		current_user = _current_user()
		if current_user:
			doc.set(fieldname, current_user)
		return

	if doc.doctype == "Pet Grooming Session" and doc.get("appointment"):
		groomer = frappe.db.get_value(
			"Pet Grooming Appointment",
			doc.appointment,
			"groomer",
		)
		if groomer:
			doc.set(fieldname, groomer)


def _can_skip_practitioner_requirement(doc) -> bool:
	if doc.doctype != "Veterinary Appointment":
		return False
	# Grooming uses the dedicated Groomer field and is validated by the unified
	# Grooming appointment bridge. It must never require or auto-populate a doctor.
	if cstr(doc.get("appointment_type") or "").strip() == "Grooming":
		return True
	return cstr(doc.get("status") or "").strip() in APPOINTMENT_PRACTITIONER_OPTIONAL_STATUSES


def _require_non_empty_user(doc, fieldname: str) -> None:
	meta = getattr(doc, "meta", None) or frappe.get_meta(doc.doctype)
	if not meta.has_field(fieldname):
		return

	value = cstr(doc.get(fieldname) or "").strip()
	if value:
		return

	label = meta.get_label(fieldname) or frappe.unscrub(fieldname)
	frappe.throw(
		_("{0} is required before this {1} can be saved.").format(label, doc.doctype),
		frappe.ValidationError,
	)


def _current_user() -> str | None:
	user = getattr(frappe.session, "user", None)
	if not user or user == "Guest":
		return None
	return user
