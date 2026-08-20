from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt
from frappe.utils import now_datetime

from vetedge.services.clinical_consultation_context import CLOSED_CONSULTATION_STATUSES
from vetedge.services.feature_flags import is_enabled
from vetedge.services.permissions import can_access_branch_data, can_access_consultation
from vetedge.services.portal_access import require_internal_user


def validate_vital_signs(doc) -> None:
	ensure_vitals_enabled()
	resolve_vitals_context(doc)
	set_vitals_title(doc)
	validate_vitals_values(doc)


def _consultation_link_is_new_or_changed(doc) -> bool:
	if not doc.get("consultation"):
		return False
	previous = doc.get_doc_before_save() if getattr(doc, "get_doc_before_save", None) else None
	return not previous or previous.get("consultation") != doc.get("consultation")


def resolve_vitals_context(doc) -> None:
	if not doc.consultation and not doc.patient:
		frappe.throw("Patient is required for Veterinary Vital Signs.", frappe.ValidationError)

	if doc.consultation:
		consultation = frappe.db.get_value(
			"Veterinary Consultation",
			doc.consultation,
			["patient", "service_branch", "status"],
			as_dict=True,
		)
		if not consultation:
			frappe.throw("Vitals must reference a valid Veterinary Consultation.", frappe.ValidationError)

		if doc.patient and doc.patient != consultation.patient:
			frappe.throw("Vitals Patient must match the linked Consultation Patient.", frappe.ValidationError)

		if doc.service_branch and doc.service_branch != consultation.service_branch:
			frappe.throw("Vitals Service Branch must match the linked Consultation Service Branch.", frappe.ValidationError)

		if _consultation_link_is_new_or_changed(doc) and consultation.get("status") in CLOSED_CONSULTATION_STATUSES:
			frappe.throw("Only an open Consultation for this patient can be linked.", frappe.ValidationError)

		doc.patient = consultation.patient
		doc.service_branch = consultation.service_branch

	if not doc.patient:
		frappe.throw("Patient is required for Veterinary Vital Signs.", frappe.ValidationError)

	if not doc.service_branch:
		patient_branch = frappe.db.get_value("Veterinary Patient", doc.patient, "default_branch")
		if patient_branch:
			doc.service_branch = patient_branch

	if not doc.service_branch:
		frappe.throw("Service Branch is required for Veterinary Vital Signs.", frappe.ValidationError)

	if not doc.recorded_by:
		doc.recorded_by = frappe.session.user

	if not doc.recorded_on:
		doc.recorded_on = frappe.utils.now_datetime()


def set_vitals_title(doc) -> None:
	patient_title = get_document_title("Veterinary Patient", doc.patient) or doc.patient
	parts = [patient_title, "Vitals"]
	if doc.recorded_on:
		parts.append(str(doc.recorded_on)[:16])
	if doc.service_branch:
		parts.append(doc.service_branch)

	doc.vitals_title = " - ".join(part for part in parts if part)


def get_document_title(doctype: str, name: str | None) -> str | None:
	if not name:
		return None

	meta = frappe.get_meta(doctype)
	title_field = meta.get_title_field()
	if title_field and title_field != "name":
		return frappe.db.get_value(doctype, name, title_field)

	return name


def validate_vitals_values(doc) -> None:
	for fieldname, label in (
		("temperature", "Temperature"),
		("weight", "Weight"),
		("heart_rate", "Heart Rate"),
		("respiratory_rate", "Respiratory Rate"),
	):
		value = doc.get(fieldname)
		if value in (None, ""):
			continue
		if flt(value) < 0:
			frappe.throw(f"{label} cannot be negative.", frappe.ValidationError)


@frappe.whitelist()
def create_vitals_from_consultation(consultation: str, values: dict | str | None = None) -> str:
	require_internal_user()
	ensure_vitals_enabled()
	if not consultation:
		frappe.throw(_("Consultation is required to create vitals."), frappe.ValidationError)

	if not frappe.has_permission("Veterinary Vital Signs", "create"):
		frappe.throw(_("Not permitted to create Veterinary Vital Signs."), frappe.PermissionError)

	values = frappe.parse_json(values or {})
	consultation_context = frappe.db.get_value(
		"Veterinary Consultation",
		consultation,
		["patient", "service_branch"],
		as_dict=True,
	)
	if not consultation_context:
		frappe.throw(_("Vitals must reference a valid Veterinary Consultation."), frappe.ValidationError)
	can_access_consultation(frappe.session.user, consultation, raise_exception=True)
	can_access_branch_data(frappe.session.user, consultation_context.service_branch, raise_exception=True)

	doc = frappe.get_doc(
		{
			"doctype": "Veterinary Vital Signs",
			"consultation": consultation,
			"patient": consultation_context.patient,
			"service_branch": consultation_context.service_branch,
			"recorded_on": values.get("recorded_on") or now_datetime(),
			"temperature": values.get("temperature"),
			"weight": values.get("weight"),
			"heart_rate": values.get("heart_rate"),
			"respiratory_rate": values.get("respiratory_rate"),
			"body_condition_score": values.get("body_condition_score"),
			"hydration_status": values.get("hydration_status"),
			"mucous_membrane": values.get("mucous_membrane"),
			"capillary_refill_time": values.get("capillary_refill_time"),
			"pain_score": values.get("pain_score"),
			"appetite_status": values.get("appetite_status"),
			"notes": values.get("notes"),
		}
	)
	doc.insert()
	return doc.name


@frappe.whitelist()
def get_latest_vitals_for_consultation(consultation: str) -> dict | None:
	require_internal_user()
	ensure_vitals_enabled()
	if not consultation:
		return None
	can_access_consultation(frappe.session.user, consultation, raise_exception=True)

	if not frappe.has_permission("Veterinary Vital Signs", "read"):
		frappe.throw("Not permitted to read Veterinary Vital Signs.", frappe.PermissionError)

	exact_match = get_latest_vitals({"consultation": consultation})
	if exact_match:
		return exact_match

	return None


def get_latest_vitals(filters: dict) -> dict | None:
	rows = frappe.get_list(
		"Veterinary Vital Signs",
		filters=filters,
		fields=[
			"name",
			"patient",
			"consultation",
			"service_branch",
			"recorded_on",
			"temperature",
			"weight",
			"heart_rate",
			"respiratory_rate",
			"body_condition_score",
			"hydration_status",
			"mucous_membrane",
			"capillary_refill_time",
			"pain_score",
			"appetite_status",
			"notes",
		],
		order_by="recorded_on desc, modified desc",
		limit=1,
	)
	return rows[0] if rows else None


def ensure_vitals_enabled() -> None:
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return

	if is_enabled("vitals"):
		return

	frappe.throw("Vitals are not enabled in Veterinary Settings.", frappe.ValidationError)