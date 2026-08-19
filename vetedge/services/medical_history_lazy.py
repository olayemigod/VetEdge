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

CLINICAL_HISTORY_WORKFLOW_CONTRACT = {
	"labs": {
		"doctype": "Veterinary Lab Order",
		"required_status": "Completed",
	},
	"vaccinations": {
		"doctype": "Veterinary Vaccination Record",
		"required_status": "Administered",
	},
}

DOCUMENT_STATUS_LABELS = {
	0: "Draft",
	1: "Submitted",
	2: "Cancelled",
}


def _validate_context(patient: str, from_date: str | None, to_date: str | None) -> tuple[str, str]:
	require_internal_user()
	can_access_medical_history(getattr(frappe.session, "user", None), patient, raise_exception=True)
	validate_patient_context(patient)
	return normalize_date_range(from_date, to_date)


def _apply_clinical_history_workflow_contract(section: str, rows: list[dict]) -> list[dict]:
	"""Keep Medical History clinical, while preserving Frappe docstatus separately.

	Lab and Vaccination records have their own clinical workflow statuses. Frappe
	docstatus is document-lifecycle metadata and must never decide whether a
	clinical event belongs in Medical History.
	"""
	contract = CLINICAL_HISTORY_WORKFLOW_CONTRACT.get(section)
	if not contract or not rows:
		return rows

	names = list(dict.fromkeys(cstr(row.get("name")).strip() for row in rows if row.get("name")))
	if not names:
		return []

	states = frappe.get_list(
		contract["doctype"],
		filters={"name": ["in", names]},
		fields=["name", "status", "docstatus"],
		page_length=len(names),
	)
	state_by_name = {cstr(row.name): row for row in states}

	result = []
	seen = set()
	for row in rows:
		name = cstr(row.get("name")).strip()
		if not name or name in seen:
			continue
		state = state_by_name.get(name)
		if not state:
			continue

		workflow_status = cstr(state.get("status")).strip()
		if workflow_status != contract["required_status"]:
			continue

		seen.add(name)
		docstatus = cint(state.get("docstatus"))
		enriched = dict(row)
		# `status` remains as a compatibility alias for older Medical History
		# consumers. New UI surfaces use workflow_status explicitly.
		enriched["workflow_status"] = workflow_status
		enriched["status"] = workflow_status
		enriched["docstatus"] = docstatus
		enriched["document_status"] = DOCUMENT_STATUS_LABELS.get(docstatus, str(docstatus))
		result.append(enriched)

	return result


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
	rows = _apply_clinical_history_workflow_contract(section, rows)
	return {
		"patient": patient,
		"section": section,
		"from_date": from_date,
		"to_date": to_date,
		"limit": limit,
		"rows": rows,
	}
