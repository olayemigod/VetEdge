from __future__ import annotations

import frappe
from frappe.utils import flt, getdate


CONSULTATION_STATUSES = {
	"Draft",
	"In Progress",
	"Awaiting Payment",
	"Ready for Treatment",
	"Completed",
	"Cancelled",
}

VALID_CONSULTATION_STATUS_TRANSITIONS = {
	"Draft": {"In Progress", "Cancelled"},
	"In Progress": {"Awaiting Payment", "Ready for Treatment", "Completed", "Cancelled"},
	"Awaiting Payment": {"Ready for Treatment", "Completed", "Cancelled"},
	"Ready for Treatment": {"Completed", "Cancelled"},
	"Completed": set(),
	"Cancelled": set(),
}


def validate_consultation(doc) -> None:
	validate_consultation_status(doc)
	resolve_consultation_context(doc)
	set_consultation_title(doc)
	validate_service_branch_access(doc)
	validate_consultation_children(doc)
	validate_completion_requirements(doc)


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


def validate_consultation_status_transition(current_status: str, target_status: str) -> None:
	allowed = VALID_CONSULTATION_STATUS_TRANSITIONS.get(current_status, set())
	if target_status not in allowed:
		frappe.throw(
			f"Consultation status cannot move from {current_status} to {target_status}.",
			frappe.ValidationError,
		)


@frappe.whitelist()
def transition_consultation_status(consultation: str, status: str) -> dict:
	doc = frappe.get_doc("Veterinary Consultation", consultation)
	validate_consultation_status_transition(doc.status, status)
	doc.status = status
	doc.save()

	return {
		"name": doc.name,
		"status": doc.status,
	}


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

	doc.consulting_practitioner_name = get_user_full_name(doc.consulting_practitioner)
	set_daily_consultation_number(doc)


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


def validate_service_branch_access(doc) -> None:
	if not doc.service_branch:
		return

	validate_user_branch_access(doc.service_branch)
	validate_practitioner_branch_access(doc.consulting_practitioner, doc.service_branch)


def validate_user_branch_access(service_branch: str) -> None:
	if not frappe.db.exists("DocType", "Branch User Assignment"):
		return

	filters = {"user": frappe.session.user, "branch": service_branch}
	if frappe.get_meta("Branch User Assignment").has_field("disabled"):
		filters["disabled"] = ["!=", 1]

	assignments = frappe.get_all(
		"Branch User Assignment",
		filters=filters,
		limit=1,
	)
	if not assignments:
		frappe.throw(
			f"User {frappe.session.user} is not assigned to Service Branch {service_branch}.",
			frappe.PermissionError,
		)


def validate_practitioner_branch_access(practitioner: str | None, service_branch: str) -> None:
	if not practitioner or not frappe.db.exists("DocType", "Branch Practitioner Assignment"):
		return

	filters = {"practitioner": practitioner, "branch": service_branch}
	if frappe.get_meta("Branch Practitioner Assignment").has_field("disabled"):
		filters["disabled"] = ["!=", 1]

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
	for row in doc.get("symptoms") or []:
		validate_enabled_link("Veterinary Symptom", row.symptom, "Symptom")

	for row in doc.get("diagnoses") or []:
		validate_enabled_link("Veterinary Diagnosis", row.diagnosis, "Diagnosis")

	for row in doc.get("planned_treatments") or []:
		if flt(row.qty) <= 0:
			frappe.throw("Planned Treatment Qty must be greater than zero.", frappe.ValidationError)
		validate_enabled_item(row.item)
		validate_enabled_link("Veterinary Service Type", row.service_type, "Service Type", required=False)
		validate_enabled_link("Veterinary Treatment Type", row.treatment_type, "Treatment Type", required=False)


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
