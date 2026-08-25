from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, cstr

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
from vetedge.services.permissions import (
	can_access_branch_data,
	get_current_user,
	get_vaccination_staff_users,
)
from vetedge.services.portal_access import require_internal_user


VACCINATION_APPOINTMENT_TYPE = "Vaccination"
VACCINATION_RECORD_DOCTYPE = "Veterinary Vaccination Record"
VACCINATION_RECORD_START_STATUSES = {"Confirmed", "Checked In"}
PAGE_LENGTH_MAX = 50


def _parse_values(values: str | dict | None) -> dict[str, Any]:
	if not values:
		return {}
	if isinstance(values, dict):
		return values
	parsed = frappe.parse_json(values)
	if not isinstance(parsed, dict):
		frappe.throw(_("Expected a JSON object."), frappe.ValidationError)
	return parsed


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


def _filter_staff_rows_by_branch(rows: list, branch: str | None) -> list:
	"""Mirror validate_practitioner_branch_access without hiding globally valid staff.

	A staff member with no Branch Practitioner Assignment rows remains available in
	all permitted branches. Once that user has explicit assignments, only those
	branches are valid. This is important for Veterinary Nurses because the existing
	assignment master is historically doctor-oriented.
	"""
	branch = cstr(branch or "").strip()
	if not rows or not branch or not frappe.db.exists("DocType", "Branch Practitioner Assignment"):
		return rows

	users = [row[0] for row in rows if row and row[0]]
	if not users:
		return rows
	meta = frappe.get_meta("Branch Practitioner Assignment")
	filters: dict[str, Any] = {"practitioner": ["in", users]}
	if meta.has_field("disabled"):
		filters["disabled"] = ["!=", 1]
	assignments = frappe.get_all(
		"Branch Practitioner Assignment",
		filters=filters,
		fields=["practitioner", "branch"],
	)
	branches_by_user: dict[str, set[str]] = {}
	for assignment in assignments:
		branches_by_user.setdefault(assignment.practitioner, set()).add(assignment.branch)
	return [
		row
		for row in rows
		if not branches_by_user.get(row[0]) or branch in branches_by_user[row[0]]
	]


@frappe.whitelist()
def search_vaccination_practitioners(
	txt: str = "",
	branch: str | None = None,
	start: int = 0,
	page_length: int = 20,
) -> list[dict[str, str]]:
	require_internal_user()
	start = max(cint(start), 0)
	page_length = min(max(cint(page_length) or 20, 1), PAGE_LENGTH_MAX)
	if branch:
		can_access_branch_data(get_current_user(), branch, raise_exception=True)
	rows = get_vaccination_staff_users("User", cstr(txt), "name", start, page_length, {})
	rows = _filter_staff_rows_by_branch(rows, branch)
	return [
		{"value": user, "label": label or user, "description": _("Vaccination Staff")}
		for user, label, *_rest in rows
	]


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_vaccination_appointment_staff(doctype, txt, searchfield, start, page_len, filters):
	"""Native Link-query equivalent of the EdgeSuite Vaccination staff search."""
	branch = cstr((filters or {}).get("branch") or "").strip()
	if branch:
		can_access_branch_data(get_current_user(), branch, raise_exception=True)
	rows = get_vaccination_staff_users(doctype, txt, searchfield, start, page_len, {})
	return _filter_staff_rows_by_branch(rows, branch)


@frappe.whitelist()
def create_edgeui_vaccination_appointment(values: str | dict | None = None) -> dict:
	require_internal_user()
	ensure_appointments_enabled()
	if not frappe.has_permission("Veterinary Appointment", "create"):
		frappe.throw(_("You are not permitted to create Veterinary Appointments."), frappe.PermissionError)
	payload = _parse_values(values)
	patient = cstr(payload.get("patient") or "").strip()
	branch = cstr(payload.get("branch") or "").strip()
	practitioner = cstr(payload.get("practitioner") or "").strip()
	vaccine = cstr(payload.get("vaccine") or "").strip()
	appointment_datetime = cstr(payload.get("appointment_datetime") or "").strip()
	if not patient or not branch or not practitioner or not vaccine or not appointment_datetime:
		frappe.throw(
			_("Patient, Service Branch, Vaccination Staff, Planned Vaccine and Appointment Date/Time are required."),
			frappe.ValidationError,
		)

	from vetedge.services.platform_access import require_vetedge_platform_access

	require_vetedge_platform_access(
		action="create_vaccination_appointment",
		reference_doctype="Veterinary Patient",
		reference_name=patient,
	)

	doc = frappe.get_doc(
		{
			"doctype": "Veterinary Appointment",
			"patient": patient,
			"branch": branch,
			"practitioner": practitioner,
			"vaccine": vaccine,
			"appointment_datetime": appointment_datetime,
			"appointment_type": VACCINATION_APPOINTMENT_TYPE,
			"status": "Scheduled",
			"created_from": "Manual",
			"notes": cstr(payload.get("notes") or "").strip(),
		}
	)
	doc.insert()
	return {
		"name": doc.name,
		"appointment_title": doc.appointment_title,
		"appointment_type": doc.appointment_type,
		"full_form_route": f"/desk/veterinary-appointment/{doc.name}",
	}


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
