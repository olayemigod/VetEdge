from __future__ import annotations

import frappe
from frappe.utils import cint, flt

from vetedge.services import medical_history as base
from vetedge.services.company_context_compat import validate_patient_history_access
from vetedge.services.portal_access import require_internal_user


def _get_vitals_trend(
	patient: str,
	fieldname: str,
	from_date: str | None,
	to_date: str | None,
	limit: int = 100,
) -> list[dict]:
	if fieldname not in base.CHARTABLE_VITAL_FIELDS:
		return []
	if not frappe.has_permission(base.VITALS_DOCTYPE, "read"):
		return []
	rows = frappe.get_list(
		base.VITALS_DOCTYPE,
		filters=base.get_date_filters("recorded_on", from_date, to_date, {"patient": patient}),
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


def _get_vitals_trends(patient: str, from_date: str, to_date: str) -> dict[str, list[dict]]:
	return {
		fieldname: _get_vitals_trend(patient, fieldname, from_date, to_date)
		for fieldname in (
			"temperature",
			"weight",
			"heart_rate",
			"respiratory_rate",
			"body_condition_score",
		)
	}


@frappe.whitelist()
def get_patient_medical_history_view(
	patient: str,
	from_date: str | None = None,
	to_date: str | None = None,
	limit: int = 100,
) -> dict:
	"""Return patient history without hiding legacy records that predate Company fields.

	Company controls which patient master can be opened. Historical consultations,
	vitals, laboratory orders and vaccinations remain linked by patient and branch;
	they are not required to carry a newly introduced Company field.
	"""
	require_internal_user()
	validate_patient_history_access(patient)
	base.validate_patient_context(patient)
	from_date, to_date = base.normalize_date_range(from_date, to_date)
	limit = cint(limit) or 100

	return {
		"patient": patient,
		"from_date": from_date,
		"to_date": to_date,
		"summary": base.get_patient_summary(patient, from_date, to_date),
		"consultations": base.get_consultation_history(patient, limit, from_date, to_date),
		"vitals": base.get_vitals_history(patient, limit, from_date, to_date),
		"diagnoses": base.get_diagnosis_history(patient, limit, from_date, to_date),
		"symptoms": base.get_symptom_history(patient, limit, from_date, to_date),
		"treatments": base.get_treatment_history(patient, limit, from_date, to_date),
		"labs": base.get_lab_history(patient, limit, from_date, to_date),
		"vaccinations": base.get_vaccination_history(patient, limit, from_date, to_date),
		"trends": _get_vitals_trends(patient, from_date, to_date),
	}
