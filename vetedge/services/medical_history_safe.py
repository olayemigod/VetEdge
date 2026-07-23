from __future__ import annotations

import frappe
from frappe.utils import cint

from vetedge.services import medical_history
from vetedge.services.permissions import can_access_medical_history
from vetedge.services.portal_access import require_internal_user

EMPTY_VITAL_TRENDS = {
    fieldname: []
    for fieldname in (
        "temperature",
        "weight",
        "heart_rate",
        "respiratory_rate",
        "body_condition_score",
    )
}


def build_permission_aware_medical_history(
    patient: str,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 100,
) -> dict:
    require_internal_user()
    can_access_medical_history(getattr(frappe.session, "user", None), patient, raise_exception=True)
    medical_history.validate_patient_context(patient)
    from_date, to_date = medical_history.normalize_date_range(from_date, to_date)
    limit = cint(limit) or 100

    can_read_consultations = frappe.has_permission(medical_history.CONSULTATION_DOCTYPE, "read")
    can_read_vitals = frappe.has_permission(medical_history.VITALS_DOCTYPE, "read")
    can_read_labs = frappe.has_permission("Veterinary Lab Order", "read")
    can_read_vaccinations = frappe.has_permission("Veterinary Vaccination Record", "read")

    return {
        "patient": patient,
        "from_date": from_date,
        "to_date": to_date,
        "summary": medical_history.get_patient_summary(patient, from_date, to_date),
        "consultations": medical_history.get_consultation_history(patient, limit, from_date, to_date)
        if can_read_consultations
        else [],
        "vitals": medical_history.get_vitals_history(patient, limit, from_date, to_date)
        if can_read_vitals
        else [],
        "diagnoses": medical_history.get_diagnosis_history(patient, limit, from_date, to_date)
        if can_read_consultations
        else [],
        "symptoms": medical_history.get_symptom_history(patient, limit, from_date, to_date)
        if can_read_consultations
        else [],
        "treatments": medical_history.get_treatment_history(patient, limit, from_date, to_date)
        if can_read_consultations
        else [],
        "labs": medical_history.get_lab_history(patient, limit, from_date, to_date)
        if can_read_labs
        else [],
        "vaccinations": medical_history.get_vaccination_history(patient, limit, from_date, to_date)
        if can_read_vaccinations
        else [],
        "trends": medical_history.get_patient_vitals_trends(patient, from_date, to_date)
        if can_read_vitals
        else {key: list(value) for key, value in EMPTY_VITAL_TRENDS.items()},
    }


@frappe.whitelist()
def get_patient_medical_history_view(
    patient: str,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 100,
) -> dict:
    return build_permission_aware_medical_history(patient, from_date, to_date, limit)


@frappe.whitelist()
def get_clinical_medical_history(
    patient: str,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 100,
) -> dict:
    return build_permission_aware_medical_history(patient, from_date, to_date, limit)
