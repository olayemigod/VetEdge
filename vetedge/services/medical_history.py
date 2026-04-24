from __future__ import annotations

import frappe
from frappe.utils import add_days, cint, flt, getdate, nowdate

from vetedge.services.lab import get_lab_history
from vetedge.services.permissions import can_access_medical_history
from vetedge.services.portal_access import require_internal_user


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
def get_patient_medical_history_view(
	patient: str,
	from_date: str | None = None,
	to_date: str | None = None,
	limit: int = 100,
) -> dict:
	require_internal_user()
	can_access_medical_history(getattr(frappe.session, "user", None), patient, raise_exception=True)
	validate_patient_context(patient)
	from_date, to_date = normalize_date_range(from_date, to_date)
	limit = cint(limit) or 100

	return {
		"patient": patient,
		"from_date": from_date,
		"to_date": to_date,
		"summary": get_patient_summary(patient, from_date, to_date),
		"consultations": get_consultation_history(patient, limit, from_date, to_date),
		"vitals": get_vitals_history(patient, limit, from_date, to_date),
		"diagnoses": get_diagnosis_history(patient, limit, from_date, to_date),
		"symptoms": get_symptom_history(patient, limit, from_date, to_date),
		"treatments": get_treatment_history(patient, limit, from_date, to_date),
		"labs": get_lab_history(patient, limit, from_date, to_date),
		"trends": get_patient_vitals_trends(patient, from_date, to_date),
		"placeholders": {
			"vaccination_history": "Deferred until vaccination records are implemented.",
		},
	}


@frappe.whitelist()
def get_patient_medical_history(
	patient: str,
	limit: int = 50,
	from_date: str | None = None,
	to_date: str | None = None,
) -> list[dict]:
	require_internal_user()
	can_access_medical_history(getattr(frappe.session, "user", None), patient, raise_exception=True)
	validate_patient_context(patient)
	from_date, to_date = normalize_date_range(from_date, to_date)
	limit = cint(limit) or 50

	events = []
	if frappe.has_permission(CONSULTATION_DOCTYPE, "read"):
		events.extend(get_consultation_history(patient, limit, from_date, to_date))
	if frappe.has_permission(VITALS_DOCTYPE, "read"):
		events.extend(get_vitals_history(patient, limit, from_date, to_date))
	if frappe.has_permission("Veterinary Lab Order", "read"):
		events.extend(get_lab_history(patient, limit, from_date, to_date))

	events.sort(key=lambda event: event.get("timestamp") or "", reverse=True)
	return events[:limit]


@frappe.whitelist()
def get_patient_vitals_trend(
	patient: str,
	fieldname: str,
	limit: int = 100,
	from_date: str | None = None,
	to_date: str | None = None,
) -> list[dict]:
	require_internal_user()
	can_access_medical_history(getattr(frappe.session, "user", None), patient, raise_exception=True)
	validate_patient_context(patient)
	from_date, to_date = normalize_date_range(from_date, to_date)
	if fieldname not in CHARTABLE_VITAL_FIELDS:
		frappe.throw(f"Unsupported vitals trend field: {fieldname}", frappe.ValidationError)

	if not frappe.has_permission(VITALS_DOCTYPE, "read"):
		frappe.throw("Not permitted to read Veterinary Vital Signs.", frappe.PermissionError)

	rows = frappe.get_list(
		VITALS_DOCTYPE,
		filters=get_date_filters("recorded_on", from_date, to_date, {"patient": patient}),
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


def get_patient_vitals_trends(patient: str, from_date: str, to_date: str) -> dict[str, list[dict]]:
	return {
		fieldname: get_patient_vitals_trend(
			patient,
			fieldname,
			from_date=from_date,
			to_date=to_date,
		)
		for fieldname in ("temperature", "weight", "heart_rate", "respiratory_rate", "body_condition_score")
	}


def validate_patient_context(patient: str) -> None:
	if not patient:
		frappe.throw("Patient is required.", frappe.ValidationError)

	if not frappe.db.exists(PATIENT_DOCTYPE, patient):
		frappe.throw("Medical history must reference a valid Veterinary Patient.", frappe.ValidationError)

	if not frappe.has_permission(PATIENT_DOCTYPE, "read"):
		frappe.throw("Not permitted to read Veterinary Patient.", frappe.PermissionError)


def normalize_date_range(from_date: str | None = None, to_date: str | None = None) -> tuple[str, str]:
	to_date = str(getdate(to_date or nowdate()))
	from_date = str(getdate(from_date or add_days(to_date, -90)))
	return from_date, to_date


def get_date_filters(fieldname: str, from_date: str | None, to_date: str | None, base_filters: dict | None = None) -> dict:
	filters = dict(base_filters or {})
	if from_date and to_date:
		filters[fieldname] = ["between", [f"{from_date} 00:00:00", f"{to_date} 23:59:59"]]
	elif from_date:
		filters[fieldname] = [">=", f"{from_date} 00:00:00"]
	elif to_date:
		filters[fieldname] = ["<=", f"{to_date} 23:59:59"]
	return filters


def get_patient_summary(patient: str, from_date: str, to_date: str) -> dict:
	patient_doc = frappe.db.get_value(
		PATIENT_DOCTYPE,
		patient,
		["patient_name", "species", "breed", "primary_owner", "default_branch"],
		as_dict=True,
	) or frappe._dict()
	latest_consultation = get_latest_consultation(patient, from_date, to_date)
	latest_vitals = get_latest_vitals(patient, from_date, to_date)

	return {
		"patient": patient,
		"patient_name": patient_doc.get("patient_name"),
		"species": patient_doc.get("species"),
		"breed": patient_doc.get("breed"),
		"primary_owner": patient_doc.get("primary_owner"),
		"default_branch": patient_doc.get("default_branch"),
		"latest_consultation_date": latest_consultation.get("consultation_datetime") if latest_consultation else None,
		"latest_weight": latest_vitals.get("weight") if latest_vitals else None,
		"latest_temperature": latest_vitals.get("temperature") if latest_vitals else None,
	}


def get_latest_consultation(patient: str, from_date: str, to_date: str):
	if not frappe.has_permission(CONSULTATION_DOCTYPE, "read"):
		return None
	rows = frappe.get_list(
		CONSULTATION_DOCTYPE,
		filters=get_date_filters("consultation_datetime", from_date, to_date, {"patient": patient}),
		fields=["name", "consultation_datetime"],
		order_by="consultation_datetime desc, modified desc",
		limit=1,
	)
	return rows[0] if rows else None


def get_latest_vitals(patient: str, from_date: str, to_date: str):
	if not frappe.has_permission(VITALS_DOCTYPE, "read"):
		return None
	rows = frappe.get_list(
		VITALS_DOCTYPE,
		filters=get_date_filters("recorded_on", from_date, to_date, {"patient": patient}),
		fields=["name", "recorded_on", "weight", "temperature"],
		order_by="recorded_on desc, modified desc",
		limit=1,
	)
	return rows[0] if rows else None


def get_consultation_history(
	patient: str,
	limit: int,
	from_date: str | None = None,
	to_date: str | None = None,
) -> list[dict]:
	consultations = frappe.get_list(
		CONSULTATION_DOCTYPE,
		filters=get_date_filters("consultation_datetime", from_date, to_date, {"patient": patient}),
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


def get_vitals_history(
	patient: str,
	limit: int,
	from_date: str | None = None,
	to_date: str | None = None,
) -> list[dict]:
	vitals = frappe.get_list(
		VITALS_DOCTYPE,
		filters=get_date_filters("recorded_on", from_date, to_date, {"patient": patient}),
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


def get_diagnosis_history(
	patient: str,
	limit: int,
	from_date: str | None = None,
	to_date: str | None = None,
) -> list[dict]:
	consultations = get_consultation_rows_for_children(patient, limit, from_date, to_date)
	consultation_by_name = {row.name: row for row in consultations}
	rows = get_child_rows("Consultation Diagnosis", list(consultation_by_name), ["diagnosis", "diagnosis_type", "notes"])

	return [
		{
			"consultation": row.parent,
			"timestamp": consultation_by_name[row.parent].consultation_datetime,
			"diagnosis": row.diagnosis,
			"diagnosis_type": row.diagnosis_type,
			"notes": row.notes,
			"practitioner": consultation_by_name[row.parent].consulting_practitioner_name,
			"service_branch": consultation_by_name[row.parent].service_branch,
		}
		for row in rows
	]


def get_symptom_history(
	patient: str,
	limit: int,
	from_date: str | None = None,
	to_date: str | None = None,
) -> list[dict]:
	consultations = get_consultation_rows_for_children(patient, limit, from_date, to_date)
	consultation_by_name = {row.name: row for row in consultations}
	rows = get_child_rows("Consultation Symptom", list(consultation_by_name), ["symptom", "notes"])

	return [
		{
			"consultation": row.parent,
			"timestamp": consultation_by_name[row.parent].consultation_datetime,
			"symptom": row.symptom,
			"notes": row.notes,
			"practitioner": consultation_by_name[row.parent].consulting_practitioner_name,
			"service_branch": consultation_by_name[row.parent].service_branch,
		}
		for row in rows
	]


def get_treatment_history(
	patient: str,
	limit: int,
	from_date: str | None = None,
	to_date: str | None = None,
) -> list[dict]:
	consultations = get_consultation_rows_for_children(patient, limit, from_date, to_date)
	consultation_by_name = {row.name: row for row in consultations}
	rows = get_child_rows(
		"Planned Treatment Item",
		list(consultation_by_name),
		["item", "qty", "uom", "service_type", "treatment_type", "notes"],
	)

	return [
		{
			"consultation": row.parent,
			"timestamp": consultation_by_name[row.parent].consultation_datetime,
			"item": row.item,
			"qty": row.qty,
			"uom": row.uom,
			"service_type": row.service_type,
			"treatment_type": row.treatment_type,
			"notes": row.notes,
			"practitioner": consultation_by_name[row.parent].consulting_practitioner_name,
			"service_branch": consultation_by_name[row.parent].service_branch,
		}
		for row in rows
	]


def get_consultation_rows_for_children(
	patient: str,
	limit: int,
	from_date: str | None = None,
	to_date: str | None = None,
) -> list:
	if not frappe.has_permission(CONSULTATION_DOCTYPE, "read"):
		return []

	return frappe.get_list(
		CONSULTATION_DOCTYPE,
		filters=get_date_filters("consultation_datetime", from_date, to_date, {"patient": patient}),
		fields=["name", "consultation_datetime", "service_branch", "consulting_practitioner_name"],
		order_by="consultation_datetime desc, modified desc",
		limit=limit,
	)


def get_child_rows(doctype: str, parent_names: list[str], fields: list[str]) -> list:
	if not parent_names:
		return []

	return frappe.get_all(
		doctype,
		filters={"parent": ["in", parent_names]},
		fields=["parent", *fields],
		order_by="parent asc, idx asc",
	)


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
