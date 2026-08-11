from __future__ import annotations

from collections.abc import Callable

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services.lab import get_lab_history
from vetedge.services.medical_history import (
	get_consultation_history,
	get_diagnosis_history,
	get_patient_summary,
	get_symptom_history,
	get_treatment_history,
	get_vitals_history,
	normalize_date_range,
	validate_patient_context,
)
from vetedge.services.permissions import can_access_medical_history
from vetedge.services.portal_access import require_internal_user
from vetedge.services.vaccination import get_vaccination_history

MEDICAL_HISTORY_SECTION_MAX_LIMIT = 100
MEDICAL_HISTORY_DEFAULT_LIMIT = 50

SECTION_READERS: dict[str, Callable] = {
	"consultations": get_consultation_history,
	"vitals": get_vitals_history,
	"diagnoses": get_diagnosis_history,
	"symptoms": get_symptom_history,
	"treatments": get_treatment_history,
	"vaccinations": get_vaccination_history,
	"labs": get_lab_history,
}


def _validate_context(patient: str, from_date: str | None, to_date: str | None) -> tuple[str, str]:
	require_internal_user()
	can_access_medical_history(getattr(frappe.session, "user", None), patient, raise_exception=True)
	validate_patient_context(patient)
	return normalize_date_range(from_date, to_date)


@frappe.whitelist()
def get_patient_medical_history_summary(
	patient: str,
	from_date: str | None = None,
	to_date: str | None = None,
) -> dict:
	"""Return only the patient/date summary needed to bootstrap Medical History."""
	from_date, to_date = _validate_context(patient, from_date, to_date)
	return {
		"patient": patient,
		"from_date": from_date,
		"to_date": to_date,
		"summary": get_patient_summary(patient, from_date, to_date),
	}


@frappe.whitelist()
def get_patient_medical_history_section(
	patient: str,
	section: str,
	limit: int = MEDICAL_HISTORY_DEFAULT_LIMIT,
	from_date: str | None = None,
	to_date: str | None = None,
) -> dict:
	"""Return one Medical History section on demand instead of the full longitudinal payload."""
	from_date, to_date = _validate_context(patient, from_date, to_date)
	section = cstr(section or "").strip().lower()
	reader = SECTION_READERS.get(section)
	if not reader:
		frappe.throw(_("Unsupported Medical History section: {0}").format(section), frappe.ValidationError)

	limit = min(
		max(cint(limit) or MEDICAL_HISTORY_DEFAULT_LIMIT, 1),
		MEDICAL_HISTORY_SECTION_MAX_LIMIT,
	)
	rows = reader(patient, limit, from_date, to_date)
	return {
		"patient": patient,
		"section": section,
		"from_date": from_date,
		"to_date": to_date,
		"limit": limit,
		"rows": rows,
	}
