from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, cstr, get_datetime

from vetedge.coreedge_adapter import get_current_vetedge_branch
from vetedge.services.guest_booking import get_default_customer_group, get_default_territory
from vetedge.services.permissions import (
	can_access_branch_data,
	get_assigned_branches,
	get_veterinary_doctor_users,
	user_has_global_branch_access,
	validate_doctor_user,
)

PAGE_LENGTH_MAX = 50
APPOINTMENT_TYPES = ("Consultation", "Follow Up", "Vaccination", "Grooming", "Boarding", "Other")
SEARCH_FIELDS = {
	"owner": {
		"doctype": "Customer",
		"fields": ["name", "customer_name", "mobile_no", "email_id"],
		"search_fields": ["name", "customer_name", "mobile_no", "email_id"],
		"label_field": "customer_name",
	},
	"patient": {
		"doctype": "Veterinary Patient",
		"fields": ["name", "patient_name", "primary_owner", "species", "breed", "microchip_id", "default_branch"],
		"search_fields": ["name", "patient_name", "primary_owner", "microchip_id"],
		"label_field": "patient_name",
	},
	"branch": {
		"doctype": "Branch",
		"fields": ["name"],
		"search_fields": ["name"],
		"label_field": "name",
	},
	"species": {
		"doctype": "Veterinary Species",
		"fields": ["name", "species_name", "description"],
		"search_fields": ["name", "species_name"],
		"label_field": "species_name",
	},
	"breed": {
		"doctype": "Veterinary Breed",
		"fields": ["name", "breed_name", "species", "description"],
		"search_fields": ["name", "breed_name", "species"],
		"label_field": "breed_name",
	},
}


def _require_login() -> None:
	if frappe.session.user == "Guest":
		frappe.throw(_("Authentication required."), frappe.PermissionError)


def _parse_values(values: str | dict | None) -> dict[str, Any]:
	if not values:
		return {}
	if isinstance(values, dict):
		return values
	parsed = frappe.parse_json(values)
	if not isinstance(parsed, dict):
		frappe.throw(_("Expected a JSON object."), frappe.ValidationError)
	return parsed


def _clean(value: Any) -> str:
	return cstr(value or "").strip()


def _option(value: Any, label: Any = None, description: Any = None, **extra) -> dict[str, Any]:
	return {
		"value": _clean(value),
		"label": _clean(label) or _clean(value),
		"description": _clean(description),
		**extra,
	}


def _get_context(context: str | dict | None) -> dict[str, Any]:
	return _parse_values(context)


def _permission_filtered_branches() -> list[str] | None:
	if user_has_global_branch_access(frappe.session.user):
		return None
	assigned = get_assigned_branches(frappe.session.user)
	return assigned or None


def _search_standard(field: str, txt: str, context: dict[str, Any], start: int, page_length: int) -> list[dict]:
	config = SEARCH_FIELDS[field]
	doctype = config["doctype"]
	if not frappe.has_permission(doctype, "read"):
		return []

	filters: dict[str, Any] = {}
	if field == "owner":
		filters["disabled"] = ["!=", 1]
	if field == "patient":
		filters["status"] = ["!=", "Deceased"]
		if context.get("owner"):
			filters["primary_owner"] = context["owner"]
		if context.get("branch"):
			filters["default_branch"] = ["in", ["", context["branch"]]]
	if field == "branch":
		branches = _permission_filtered_branches()
		if branches:
			filters["name"] = ["in", branches]
	if field == "species":
		filters["disabled"] = ["!=", 1]
	if field == "breed":
		filters["disabled"] = ["!=", 1]
		if context.get("species"):
			filters["species"] = context["species"]

	or_filters = None
	if txt:
		pattern = f"%{txt}%"
		or_filters = [[doctype, fieldname, "like", pattern] for fieldname in config["search_fields"]]

	rows = frappe.get_list(
		doctype,
		fields=config["fields"],
		filters=filters,
		or_filters=or_filters,
		order_by=f"{config['label_field']} asc",
		start=start,
		page_length=page_length,
	)

	options = []
	for row in rows:
		if field == "owner":
			description = " · ".join(filter(None, [row.get("mobile_no"), row.get("email_id")]))
		elif field == "patient":
			description = " · ".join(filter(None, [row.get("primary_owner"), row.get("species"), row.get("breed")]))
		elif field == "breed":
			description = " · ".join(filter(None, [row.get("species"), row.get("description")]))
		else:
			description = row.get("description") or ""
		options.append(_option(row.get("name"), row.get(config["label_field"]), description, raw=row))
	return options


def _search_practitioners(txt: str, context: dict[str, Any], start: int, page_length: int) -> list[dict]:
	rows = get_veterinary_doctor_users("User", txt, "name", start, page_length, {})
	branch = _clean(context.get("branch"))
	allowed: set[str] | None = None
	if branch and frappe.db.exists("DocType", "Branch Practitioner Assignment"):
		assignment_meta = frappe.get_meta("Branch Practitioner Assignment")
		filters: dict[str, Any] = {"branch": branch}
		if assignment_meta.has_field("disabled"):
			filters["disabled"] = ["!=", 1]
		assigned = set(frappe.get_all("Branch Practitioner Assignment", filters=filters, pluck="practitioner"))
		if assigned:
			allowed = assigned

	return [
		_option(user, label, "Veterinary Doctor")
		for user, label, *_rest in rows
		if allowed is None or user in allowed
	]


@frappe.whitelist()
def get_appointment_form_bootstrap() -> dict[str, Any]:
	_require_login()
	default_branch = get_current_vetedge_branch()
	if default_branch and _clean(default_branch).lower() in {"all", "all branches"}:
		default_branch = None
	return {
		"default_branch": default_branch,
		"appointment_types": list(APPOINTMENT_TYPES),
		"can_create_owner": bool(frappe.has_permission("Customer", "create")),
		"can_create_patient": bool(frappe.has_permission("Veterinary Patient", "create")),
		"can_create_appointment": bool(frappe.has_permission("Veterinary Appointment", "create")),
	}


@frappe.whitelist()
def search_appointment_link(
	field: str,
	txt: str = "",
	context: str | dict | None = None,
	start: int = 0,
	page_length: int = 20,
) -> list[dict]:
	_require_login()
	field = _clean(field)
	start = max(cint(start), 0)
	page_length = min(max(cint(page_length) or 20, 1), PAGE_LENGTH_MAX)
	context_values = _get_context(context)
	if field == "practitioner":
		return _search_practitioners(_clean(txt), context_values, start, page_length)
	if field not in SEARCH_FIELDS:
		frappe.throw(_("This appointment field is not available for EdgeSuite search."), frappe.PermissionError)
	return _search_standard(field, _clean(txt), context_values, start, page_length)


def _find_owner_duplicate(mobile_no: str, email_id: str) -> str | None:
	or_filters = []
	if mobile_no:
		or_filters.append(["Customer", "mobile_no", "=", mobile_no])
	if email_id:
		or_filters.append(["Customer", "email_id", "=", email_id])
	if not or_filters:
		return None
	rows = frappe.get_list("Customer", fields=["name"], or_filters=or_filters, page_length=1)
	return rows[0].name if rows else None


@frappe.whitelist()
def create_appointment_owner(values: str | dict) -> dict[str, Any]:
	_require_login()
	if not frappe.has_permission("Customer", "create"):
		frappe.throw(_("You are not permitted to create pet owners."), frappe.PermissionError)

	payload = _parse_values(values)
	owner_name = _clean(payload.get("owner_name") or payload.get("customer_name"))
	mobile_no = _clean(payload.get("mobile_no"))
	email_id = _clean(payload.get("email_id")).lower()
	if not owner_name:
		frappe.throw(_("Owner Name is required."), frappe.ValidationError)
	if not (mobile_no or email_id):
		frappe.throw(_("Mobile Number or Email is required."), frappe.ValidationError)

	duplicate = _find_owner_duplicate(mobile_no, email_id)
	if duplicate:
		frappe.throw(_("An owner already exists with this mobile number or email: {0}").format(duplicate), frappe.DuplicateEntryError)

	customer_group = get_default_customer_group()
	territory = get_default_territory()
	if not customer_group or not territory:
		frappe.throw(_("Configure a default Customer Group and Territory before creating owners."), frappe.ValidationError)

	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": owner_name,
			"customer_type": "Individual",
			"customer_group": customer_group,
			"territory": territory,
			"mobile_no": mobile_no,
			"email_id": email_id,
		}
	)
	doc.insert()
	return _option(doc.name, doc.customer_name, " · ".join(filter(None, [doc.mobile_no, doc.email_id])))


def _find_patient_duplicate(owner: str, patient_name: str, microchip_id: str) -> str | None:
	if microchip_id:
		duplicate = frappe.get_list(
			"Veterinary Patient",
			fields=["name"],
			filters={"microchip_id": microchip_id},
			page_length=1,
		)
		if duplicate:
			return duplicate[0].name
	rows = frappe.get_list(
		"Veterinary Patient",
		fields=["name"],
		filters={"primary_owner": owner, "patient_name": patient_name, "status": ["!=", "Deceased"]},
		page_length=1,
	)
	return rows[0].name if rows else None


@frappe.whitelist()
def create_appointment_patient(values: str | dict) -> dict[str, Any]:
	_require_login()
	if not frappe.has_permission("Veterinary Patient", "create"):
		frappe.throw(_("You are not permitted to create Veterinary Patients."), frappe.PermissionError)

	payload = _parse_values(values)
	patient_name = _clean(payload.get("patient_name"))
	owner = _clean(payload.get("primary_owner"))
	branch = _clean(payload.get("default_branch") or get_current_vetedge_branch())
	species = _clean(payload.get("species"))
	breed = _clean(payload.get("breed"))
	microchip_id = _clean(payload.get("microchip_id"))
	if not patient_name or not owner or not species:
		frappe.throw(_("Patient Name, Primary Owner and Species are required."), frappe.ValidationError)
	if not frappe.db.exists("Customer", owner):
		frappe.throw(_("Primary Owner is not a valid Customer."), frappe.ValidationError)
	if branch:
		can_access_branch_data(frappe.session.user, branch, raise_exception=True)
	if not frappe.db.exists("Veterinary Species", species):
		frappe.throw(_("Species is not valid."), frappe.ValidationError)
	if breed:
		breed_species = frappe.db.get_value("Veterinary Breed", breed, "species")
		if not breed_species or breed_species != species:
			frappe.throw(_("Breed must belong to the selected Species."), frappe.ValidationError)

	duplicate = _find_patient_duplicate(owner, patient_name, microchip_id)
	if duplicate:
		frappe.throw(_("A matching Veterinary Patient already exists: {0}").format(duplicate), frappe.DuplicateEntryError)

	doc = frappe.get_doc(
		{
			"doctype": "Veterinary Patient",
			"patient_name": patient_name,
			"primary_owner": owner,
			"default_branch": branch,
			"species": species,
			"breed": breed,
			"sex": _clean(payload.get("sex")),
			"color_markings": _clean(payload.get("color_markings")),
			"microchip_id": microchip_id,
			"status": "Active",
		}
	)
	doc.insert()
	return _option(doc.name, doc.patient_name, " · ".join(filter(None, [doc.primary_owner, doc.species, doc.breed])))


@frappe.whitelist()
def create_edgeui_appointment(values: str | dict) -> dict[str, Any]:
	_require_login()
	if not frappe.has_permission("Veterinary Appointment", "create"):
		frappe.throw(_("You are not permitted to create Veterinary Appointments."), frappe.PermissionError)

	payload = _parse_values(values)
	patient = _clean(payload.get("patient"))
	branch = _clean(payload.get("branch"))
	practitioner = _clean(payload.get("practitioner"))
	appointment_datetime = _clean(payload.get("appointment_datetime"))
	appointment_type = _clean(payload.get("appointment_type") or "Consultation")
	if not patient or not branch or not practitioner or not appointment_datetime:
		frappe.throw(_("Patient, Branch, Practitioner and Appointment Date/Time are required."), frappe.ValidationError)
	if appointment_type not in APPOINTMENT_TYPES:
		frappe.throw(_("Appointment Type is invalid."), frappe.ValidationError)

	patient_values = frappe.db.get_value(
		"Veterinary Patient",
		patient,
		["primary_owner", "status", "default_branch"],
		as_dict=True,
	)
	if not patient_values or patient_values.status == "Deceased":
		frappe.throw(_("Select an active Veterinary Patient."), frappe.ValidationError)
	can_access_branch_data(frappe.session.user, branch, raise_exception=True)
	validate_doctor_user(practitioner)
	get_datetime(appointment_datetime)

	doc = frappe.get_doc(
		{
			"doctype": "Veterinary Appointment",
			"patient": patient,
			"primary_owner": patient_values.primary_owner,
			"branch": branch,
			"practitioner": practitioner,
			"appointment_datetime": appointment_datetime,
			"appointment_type": appointment_type,
			"status": "Scheduled",
			"created_from": "Manual",
			"notes": _clean(payload.get("notes")),
		}
	)
	doc.insert()
	return {
		"name": doc.name,
		"appointment_title": doc.appointment_title,
		"full_form_route": f"/app/veterinary-appointment/{doc.name}",
	}
