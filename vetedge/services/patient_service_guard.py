from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint


PATIENT_FIELD_CANDIDATES = ("patient", "veterinary_patient", "animal", "pet")

# Existing historical records may still need result entry, discharge, cancellation,
# audit notes or financial cleanup after a Patient dies. Only transitions that
# deliver/commence a new clinical service are blocked here.
BLOCKED_DELIVERY_TRANSITIONS = {
    "Veterinary Appointment": {
        "Scheduled",
        "Confirmed",
        "Checked In",
        "In Consultation",
        "Completed",
    },
    "Veterinary Consultation": {
        "In Progress",
        "Awaiting Payment",
        "Ready for Treatment",
        "Treatment In Progress",
        "Completed",
    },
    "Veterinary Vaccination Record": {"Pending Administration", "Administered"},
    "Pet Grooming Appointment": {"Confirmed", "Checked In", "In Progress", "Completed"},
    "Pet Grooming Session": {"In Progress", "Completed"},
    "Pet Boarding Booking": {"Confirmed", "Checked In", "Admitted", "In Stay", "Completed"},
    "Pet Boarding Stay": {"Admitted", "In Stay", "Active"},
}


def _patient_name(doc) -> str | None:
    for fieldname in PATIENT_FIELD_CANDIDATES:
        value = doc.get(fieldname)
        if value:
            return str(value)
    return None


def patient_is_deceased(patient: str | None) -> bool:
    if not patient or not frappe.db.exists("Veterinary Patient", patient):
        return False
    values = frappe.db.get_value(
        "Veterinary Patient", patient, ["status", "is_deceased"], as_dict=True
    )
    return bool(values and (values.status == "Deceased" or cint(values.is_deceased)))


def assert_patient_accepts_new_service(patient: str | None, service_label: str = "clinical service") -> None:
    if not patient_is_deceased(patient):
        return
    label = frappe.db.get_value("Veterinary Patient", patient, "patient_name") or patient
    frappe.throw(
        _("{0} is recorded as deceased. A new {1} cannot be created or delivered for this Patient.").format(
            label, service_label
        ),
        frappe.ValidationError,
    )


def enforce_patient_service_guard(doc, method: str | None = None) -> None:
    patient = _patient_name(doc)
    if not patient or not patient_is_deceased(patient):
        return

    is_new_method = getattr(doc, "is_new", None)
    is_new = bool(is_new_method()) if callable(is_new_method) else not bool(doc.get("name"))
    if is_new:
        assert_patient_accepts_new_service(patient, doc.doctype)

    blocked = BLOCKED_DELIVERY_TRANSITIONS.get(doc.doctype, set())
    if not blocked or not doc.meta.has_field("status"):
        return

    previous = doc.get_doc_before_save() if getattr(doc, "get_doc_before_save", None) else None
    current_status = str(doc.get("status") or "")
    previous_status = str(previous.get("status") or "") if previous else ""
    if current_status != previous_status and current_status in blocked:
        assert_patient_accepts_new_service(patient, current_status)
