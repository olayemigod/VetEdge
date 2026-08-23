from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cstr

from vetedge.services.appointment_flow import (
	ensure_appointments_enabled,
	normalize_consultation_links,
	set_appointment_title,
	validate_appointment_datetime,
	validate_duplicate_practitioner_slot,
	validate_status,
)
from vetedge.services.appointment_intelligence import (
	prepare_appointment_service_context,
	resolve_appointment_vaccine,
	validate_appointment_service_context,
)
from vetedge.services.consultation_flow import (
	get_user_full_name,
	validate_practitioner_branch_access,
	validate_user_branch_access,
)
from vetedge.services.permissions import can_access_branch_data, get_current_user
from vetedge.services.portal_access import require_internal_user


VACCINATION_APPOINTMENT_TYPE = "Vaccination"
VACCINATION_RECORD_DOCTYPE = "Veterinary Vaccination Record"
VACCINATION_RECORD_START_STATUSES = {"Confirmed", "Checked In"}


def is_vaccination_veterinary_appointment(doc) -> bool:
	return bool(doc and cstr(doc.get("appointment_type") or "").strip() == VACCINATION_APPOINTMENT_TYPE)


def validate_vaccination_veterinary_appointment(doc) -> None:
	"""Validate Vaccination scheduling using staff roles that may administer vaccines.

	Veterinary Appointment remains the scheduling truth. Veterinary Vaccination Record
	remains the billing, stock, batch, payment and administration truth.
	"""
	ensure_appointments_enabled()
	prepare_appointment_service_context(doc)
	normalize_consultation_links(doc)
	validate_status(doc)
	_resolve_vaccination_appointment_context(doc)
	validate_appointment_datetime(doc)
	_validate_vaccination_appointment_branch_access(doc)
	validate_appointment_service_context(doc)
	validate_duplicate_practitioner_slot(doc)
	set_appointment_title(doc)


def _resolve_vaccination_appointment_context(doc) -> None:
	if not doc.patient:
		frappe.throw(_("Patient is required for a Vaccination appointment."), frappe.ValidationError)
	patient = frappe.db.get_value(
		"Veterinary Patient",
		doc.patient,
		["primary_owner", "default_branch", "status"],
		as_dict=True,
	)
	if not patient or patient.get("status") == "Deceased":
		frappe.throw(_("Select an active Veterinary Patient."), frappe.ValidationError)
	if not patient.primary_owner:
		frappe.throw(_("Patient must have a Primary Owner before appointment booking."), frappe.ValidationError)

	doc.primary_owner = patient.primary_owner
	if not doc.branch:
		doc.branch = patient.default_branch
	if not doc.branch:
		frappe.throw(_("Branch is required for a Vaccination appointment."), frappe.ValidationError)
	if not doc.created_from:
		doc.created_from = "Manual"
	if doc.get("linked_consultation"):
		frappe.throw(
			_("A Vaccination appointment cannot remain linked to a Consultation. Use the Vaccination workflow instead."),
			frappe.ValidationError,
		)

	if doc.practitioner:
		from vetedge.services.vaccination import can_administer_vaccine

		can_administer_vaccine(doc.practitioner, raise_exception=True)
	doc.practitioner_name = get_user_full_name(doc.practitioner)


def _validate_vaccination_appointment_branch_access(doc) -> None:
	if not doc.branch:
		return
	if doc.created_from == "Guest" and doc.status == "Awaiting Registration":
		return
	if doc.created_from == "Portal" and doc.status == "Owner Requested":
		return
	validate_user_branch_access(doc.branch)
	validate_practitioner_branch_access(doc.practitioner, doc.branch)


def get_linked_vaccination_record_name(appointment: str | None) -> str | None:
	if not appointment or not frappe.db.exists("DocType", VACCINATION_RECORD_DOCTYPE):
		return None
	meta = frappe.get_meta(VACCINATION_RECORD_DOCTYPE)
	if not meta.has_field("linked_appointment"):
		return None
	return frappe.db.get_value(VACCINATION_RECORD_DOCTYPE, {"linked_appointment": appointment}, "name")


def validate_vaccination_record_appointment_link(doc) -> None:
	appointment_name = cstr(doc.get("linked_appointment") or "").strip()
	if not appointment_name:
		return

	appointment = frappe.db.get_value(
		"Veterinary Appointment",
		appointment_name,
		["name", "appointment_type", "patient", "branch", "vaccine"],
		as_dict=True,
	)
	if not appointment:
		frappe.throw(_("Linked Appointment must be a valid Veterinary Appointment."), frappe.ValidationError)
	if appointment.appointment_type != VACCINATION_APPOINTMENT_TYPE:
		frappe.throw(_("Linked Appointment must be a Vaccination appointment."), frappe.ValidationError)
	if appointment.patient and doc.get("patient") and appointment.patient != doc.patient:
		frappe.throw(_("Linked Vaccination Appointment must belong to the selected patient."), frappe.ValidationError)
	if appointment.branch and doc.get("service_branch") and appointment.branch != doc.service_branch:
		frappe.throw(_("Vaccination Record branch must match its linked Appointment branch."), frappe.ValidationError)
	planned_vaccine = cstr(appointment.get("vaccine") or "").strip()
	if planned_vaccine and doc.get("vaccine") and planned_vaccine != doc.vaccine:
		frappe.throw(_("Vaccination Record vaccine must match the vaccine planned on its linked Appointment."), frappe.ValidationError)
	if appointment.branch:
		can_access_branch_data(get_current_user(), appointment.branch, raise_exception=True)

	existing = frappe.db.get_value(
		VACCINATION_RECORD_DOCTYPE,
		{"linked_appointment": appointment_name, "name": ["!=", doc.name or ""]},
		"name",
	)
	if existing:
		frappe.throw(
			_("Vaccination Appointment {0} is already linked to Vaccination Record {1}.").format(
				appointment_name, existing
			),
			frappe.ValidationError,
		)


@frappe.whitelist()
def create_or_open_vaccination_record_from_appointment(appointment: str) -> dict:
	require_internal_user()
	ensure_appointments_enabled()
	appointment_doc = frappe.get_doc("Veterinary Appointment", appointment)
	appointment_doc.check_permission("read")
	appointment_doc.check_permission("write")
	if not is_vaccination_veterinary_appointment(appointment_doc):
		frappe.throw(_("Only Vaccination appointments can create Vaccination Records."), frappe.ValidationError)
	if appointment_doc.status not in VACCINATION_RECORD_START_STATUSES:
		frappe.throw(
			_("Vaccination appointment must be Confirmed or Checked In before its Vaccination Record is created."),
			frappe.ValidationError,
		)
	if appointment_doc.branch:
		can_access_branch_data(get_current_user(), appointment_doc.branch, raise_exception=True)

	from vetedge.services.platform_access import require_vetedge_platform_access

	require_vetedge_platform_access(
		action="create_vaccination_record_from_appointment",
		reference_doctype=appointment_doc.doctype,
		reference_name=appointment_doc.name,
	)

	existing_name = get_linked_vaccination_record_name(appointment_doc.name)
	if existing_name:
		existing = frappe.get_doc(VACCINATION_RECORD_DOCTYPE, existing_name)
		existing.check_permission("read")
		return {"name": existing.name, "status": existing.status, "created": False}

	if not frappe.has_permission(VACCINATION_RECORD_DOCTYPE, "create"):
		frappe.throw(_("You are not permitted to create Vaccination Records."), frappe.PermissionError)

	vaccine = resolve_appointment_vaccine(appointment_doc)
	if not vaccine:
		frappe.throw(_("A Planned Vaccine is required before creating the Vaccination Record."), frappe.ValidationError)

	record = frappe.get_doc(
		{
			"doctype": VACCINATION_RECORD_DOCTYPE,
			"linked_appointment": appointment_doc.name,
			"patient": appointment_doc.patient,
			"primary_owner": appointment_doc.primary_owner,
			"service_branch": appointment_doc.branch,
			"vaccine": vaccine,
			"status": "Draft",
			"notes": appointment_doc.notes,
		}
	)
	record.insert()
	return {"name": record.name, "status": record.status, "created": True}
