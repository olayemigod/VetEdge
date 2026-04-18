from __future__ import annotations

import frappe
from frappe.utils import cint, flt


CONSULTATION_DOCTYPE = "Veterinary Consultation"
VITALS_DOCTYPE = "Veterinary Vital Signs"
PATIENT_DOCTYPE = "Veterinary Patient"

CHARTABLE_VITAL_FIELDS = {
	"temperature",
	"weight",
	"heart_rate",
	"respiratory_rate",
	"body_condition_score",
	"pain_score",
}


@frappe.whitelist()
def get_patient_medical_history(patient: str, limit: int = 50) -> list[dict]:
	validate_patient_context(patient)
	limit = cint(limit) or 50

	events = []
	if frappe.has_permission(CONSULTATION_DOCTYPE, "read"):
		events.extend(get_consultation_history(patient, limit))
	if frappe.has_permission(VITALS_DOCTYPE, "read"):
		events.extend(get_vitals_history(patient, limit))

	events.sort(key=lambda event: event.get("timestamp") or "", reverse=True)
	return events[:limit]


@frappe.whitelist()
def get_patient_vitals_trend(patient: str, fieldname: str, limit: int = 100) -> list[dict]:
	validate_patient_context(patient)
	if fieldname not in CHARTABLE_VITAL_FIELDS:
		frappe.throw(f"Unsupported vitals trend field: {fieldname}", frappe.ValidationError)

	if not frappe.has_permission(VITALS_DOCTYPE, "read"):
		frappe.throw("Not permitted to read Veterinary Vital Signs.", frappe.PermissionError)

	rows = frappe.get_list(
		VITALS_DOCTYPE,
		filters={"patient": patient},
		fields=["name", "recorded_on", fieldname],
		order_by="recorded_on asc, modified asc",
		limit=cint(limit) or 100,
	)

	return [
		{
			"name": row.name,
			"timestamp": row.recorded_on,
			"fieldname": fieldname,
			"value": flt(row.get(fieldname)),
		}
		for row in rows
		if row.get(fieldname) not in (None, "")
	]


def validate_patient_context(patient: str) -> None:
	if not patient:
		frappe.throw("Patient is required.", frappe.ValidationError)

	if not frappe.db.exists(PATIENT_DOCTYPE, patient):
		frappe.throw("Medical history must reference a valid Veterinary Patient.", frappe.ValidationError)

	if not frappe.has_permission(PATIENT_DOCTYPE, "read"):
		frappe.throw("Not permitted to read Veterinary Patient.", frappe.PermissionError)


def get_consultation_history(patient: str, limit: int) -> list[dict]:
	consultations = frappe.get_list(
		CONSULTATION_DOCTYPE,
		filters={"patient": patient},
		fields=[
			"name",
			"consultation_title",
			"consultation_datetime",
			"service_branch",
			"consulting_practitioner_name",
			"status",
			"presenting_complaint",
			"assessment_notes",
			"treatment_plan_summary",
		],
		order_by="consultation_datetime desc, modified desc",
		limit=limit,
	)

	consultation_names = [row.name for row in consultations]
	symptoms_by_consultation = get_child_values(
		"Consultation Symptom",
		consultation_names,
		"symptom",
		"notes",
	)
	diagnoses_by_consultation = get_child_values(
		"Consultation Diagnosis",
		consultation_names,
		"diagnosis",
		"notes",
	)

	return [
		{
			"type": "consultation",
			"name": row.name,
			"title": row.consultation_title or row.name,
			"timestamp": row.consultation_datetime,
			"service_branch": row.service_branch,
			"practitioner": row.consulting_practitioner_name,
			"status": row.status,
			"presenting_complaint": row.presenting_complaint,
			"assessment_notes": row.assessment_notes,
			"treatment_plan_summary": row.treatment_plan_summary,
			"symptoms": symptoms_by_consultation.get(row.name, []),
			"diagnoses": diagnoses_by_consultation.get(row.name, []),
		}
		for row in consultations
	]


def get_vitals_history(patient: str, limit: int) -> list[dict]:
	vitals = frappe.get_list(
		VITALS_DOCTYPE,
		filters={"patient": patient},
		fields=[
			"name",
			"vitals_title",
			"consultation",
			"recorded_on",
			"service_branch",
			"recorded_by",
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
		limit=limit,
	)

	return [
		{
			"type": "vitals",
			"name": row.name,
			"title": row.vitals_title or row.name,
			"timestamp": row.recorded_on,
			"consultation": row.consultation,
			"service_branch": row.service_branch,
			"recorded_by": row.recorded_by,
			"temperature": row.temperature,
			"weight": row.weight,
			"heart_rate": row.heart_rate,
			"respiratory_rate": row.respiratory_rate,
			"body_condition_score": row.body_condition_score,
			"hydration_status": row.hydration_status,
			"mucous_membrane": row.mucous_membrane,
			"capillary_refill_time": row.capillary_refill_time,
			"pain_score": row.pain_score,
			"appetite_status": row.appetite_status,
			"notes": row.notes,
		}
		for row in vitals
	]


def get_child_values(
	doctype: str,
	parent_names: list[str],
	value_field: str,
	notes_field: str | None = None,
) -> dict[str, list[dict]]:
	if not parent_names:
		return {}

	fields = ["parent", value_field]
	if notes_field:
		fields.append(notes_field)

	rows = frappe.get_all(
		doctype,
		filters={"parent": ["in", parent_names]},
		fields=fields,
		order_by="idx asc",
	)

	values = {}
	for row in rows:
		values.setdefault(row.parent, []).append(
			{
				"value": row.get(value_field),
				"notes": row.get(notes_field) if notes_field else None,
			}
		)

	return values
