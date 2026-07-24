from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

from vetedge.services.permissions import (
	ELEVATED_ROLES,
	ROLE_VETEDGE_DOCTOR,
	can_access_patient,
	get_current_user,
	get_user_roles,
	get_veterinary_doctor_users,
)
from vetedge.services.portal_access import require_internal_user


def is_restricted_doctor(user: str | None = None) -> bool:
	user = user or get_current_user()
	roles = get_user_roles(user)
	return ROLE_VETEDGE_DOCTOR in roles and not bool(roles & ELEVATED_ROLES)


def assert_consultation_write_ownership(
	consultation: str | None = None,
	*,
	doc=None,
	action: str = "save",
	user: str | None = None,
) -> None:
	user = user or get_current_user()
	if not is_restricted_doctor(user):
		return

	if doc is None and consultation:
		doc = frappe.get_doc("Veterinary Consultation", consultation)
	if doc is None:
		return

	assigned = doc.get("consulting_practitioner")
	if assigned == user:
		return

	frappe.throw(
		_("Doctors can only {0} consultations assigned to themselves.").format(
			{"save": _("save"), "transition": _("update"), "vitals": _("record vitals for")}.get(
				action,
				_("update"),
			)
		),
		frappe.PermissionError,
	)


def enforce_consultation_practitioner_ownership(doc, method: str | None = None) -> None:
	user = get_current_user()
	if not is_restricted_doctor(user):
		return

	previous = doc.get_doc_before_save()
	if previous and previous.get("consulting_practitioner") != user:
		frappe.throw(
			_("This consultation belongs to another doctor and cannot be reassigned or saved by you."),
			frappe.PermissionError,
		)

	selected = doc.get("consulting_practitioner")
	if selected and selected != user:
		frappe.throw(
			_("A doctor cannot save a consultation for another doctor."),
			frappe.PermissionError,
		)

	doc.consulting_practitioner = user


def enforce_vitals_consultation_ownership(doc, method: str | None = None) -> None:
	consultation = doc.get("consultation")
	if consultation:
		assert_consultation_write_ownership(consultation, action="vitals")


def _document_title(doctype: str, name: str | None) -> str | None:
	if not name:
		return None
	meta = frappe.get_meta(doctype)
	fieldname = meta.title_field or "name"
	return frappe.db.get_value(doctype, name, fieldname) or name


def _match(value: str | None, query: str) -> bool:
	if not query:
		return True
	return query.casefold() in str(value or "").casefold()


@frappe.whitelist()
def get_clinical_context_options(kind: str, search: str = "", limit: int = 20) -> list[dict[str, Any]]:
	require_internal_user()
	query = str(search or "").strip()
	page_len = min(max(cint(limit) or 20, 1), 50)

	if kind == "practitioner":
		user = get_current_user()
		if is_restricted_doctor(user):
			label = _document_title("User", user) or user
			if not (_match(user, query) or _match(label, query)):
				return []
			return [{"value": user, "label": label}]

		rows = get_veterinary_doctor_users("User", query, "name", 0, page_len, {})
		return [{"value": row[0], "label": row[1]} for row in rows]

	if kind != "consultation_type":
		frappe.throw(_("Unsupported clinical context option type."), frappe.ValidationError)

	meta = frappe.get_meta("Consultation Type")
	filters: dict[str, Any] = {}
	if meta.has_field("disabled"):
		filters["disabled"] = 0
	fields = ["name", "consultation_type"]
	for fieldname in ("description", "sort_order"):
		if meta.has_field(fieldname):
			fields.append(fieldname)
	or_filters = None
	if query:
		or_filters = [
			["Consultation Type", "name", "like", f"%{query}%"],
			["Consultation Type", "consultation_type", "like", f"%{query}%"],
		]
	order_by = "sort_order asc, consultation_type asc" if meta.has_field("sort_order") else "consultation_type asc"
	rows = frappe.get_list(
		"Consultation Type",
		fields=fields,
		filters=filters,
		or_filters=or_filters,
		order_by=order_by,
		page_length=page_len,
	)
	return [
		{
			"value": row.get("name"),
			"label": row.get("consultation_type") or row.get("name"),
			"description": row.get("description") or "",
		}
		for row in rows
	]


@frappe.whitelist()
def get_patient_owner_context(patient: str) -> dict[str, Any]:
	require_internal_user()
	if not patient:
		return {}
	if not frappe.has_permission("Veterinary Patient", "read", patient):
		frappe.throw(_("You are not permitted to view this Veterinary Patient."), frappe.PermissionError)
	can_access_patient(get_current_user(), patient, raise_exception=True)

	patient_meta = frappe.get_meta("Veterinary Patient")
	patient_fields = ["name", "patient_name", "primary_owner", "default_branch"]
	for fieldname in ("species", "breed", "emergency_contact"):
		if patient_meta.has_field(fieldname):
			patient_fields.append(fieldname)
	patient_row = frappe.db.get_value(
		"Veterinary Patient",
		patient,
		patient_fields,
		as_dict=True,
	)
	if not patient_row:
		frappe.throw(_("Veterinary Patient could not be found."), frappe.DoesNotExistError)

	owner_name = patient_row.get("primary_owner")
	owner: dict[str, Any] = {
		"name": owner_name,
		"label": _document_title("Customer", owner_name) if owner_name else None,
		"mobile_no": None,
		"email_id": None,
	}
	if owner_name:
		customer_meta = frappe.get_meta("Customer")
		customer_fields = ["name"]
		for fieldname in ("customer_name", "mobile_no", "email_id"):
			if customer_meta.has_field(fieldname):
				customer_fields.append(fieldname)
		customer_row = frappe.db.get_value("Customer", owner_name, customer_fields, as_dict=True) or {}
		owner.update(
			{
				"label": customer_row.get("customer_name") or owner.get("label") or owner_name,
				"mobile_no": customer_row.get("mobile_no"),
				"email_id": customer_row.get("email_id"),
			}
		)

	return {
		"patient": {
			"name": patient_row.get("name"),
			"label": patient_row.get("patient_name") or patient_row.get("name"),
			"default_branch": patient_row.get("default_branch"),
			"species": patient_row.get("species"),
			"breed": patient_row.get("breed"),
			"emergency_contact": patient_row.get("emergency_contact"),
		},
		"owner": owner,
	}
