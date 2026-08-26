from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cstr


PATIENT_DOCTYPE = "Veterinary Patient"
CONSULTATION_DOCTYPE = "Veterinary Consultation"


def _clean(value) -> str:
    return cstr(value or "").strip()


def _patient_context(patient_name: str) -> dict:
    row = frappe.db.get_value(
        PATIENT_DOCTYPE,
        patient_name,
        ["name", "patient_name", "primary_owner", "default_branch"],
        as_dict=True,
    )
    if not row:
        frappe.throw(_("Hospitalisation must reference a valid Veterinary Patient."), frappe.ValidationError)
    if not _clean(row.get("primary_owner")):
        frappe.throw(_("The selected Patient must have a Primary Owner before Hospitalisation."), frappe.ValidationError)
    return row


def _consultation_context(consultation_name: str) -> dict:
    row = frappe.db.get_value(
        CONSULTATION_DOCTYPE,
        consultation_name,
        [
            "name",
            "patient",
            "primary_owner",
            "service_branch",
            "company",
            "consulting_practitioner",
        ],
        as_dict=True,
    )
    if not row:
        frappe.throw(_("Linked Consultation must be a valid Veterinary Consultation."), frappe.ValidationError)
    return row


def _set_if_missing(doc, fieldname: str, value) -> None:
    if value not in (None, "") and not _clean(doc.get(fieldname)):
        doc.set(fieldname, value)


def _require_same(label: str, actual, expected) -> None:
    actual_value = _clean(actual)
    expected_value = _clean(expected)
    if actual_value and expected_value and actual_value != expected_value:
        frappe.throw(
            _("Hospitalisation {0} must match the linked Consultation.").format(label),
            frappe.ValidationError,
        )


def _previous_doc(doc):
    getter = getattr(doc, "get_doc_before_save", None)
    return getter() if callable(getter) else None


def _is_unchanged_historical_owner(doc, previous, patient_name: str) -> bool:
    if not previous:
        return False
    return bool(
        _clean(previous.get("patient")) == patient_name
        and _clean(previous.get("customer"))
        and _clean(previous.get("customer")) == _clean(doc.get("customer"))
    )


def resolve_hospitalisation_context(doc) -> None:
    """Normalize and validate Hospitalisation clinical context.

    Patient.default_branch is a fallback only. A linked Consultation, when
    supplied, is authoritative for Patient, Owner, service Branch and Company.
    Existing direct admissions preserve their recorded episode owner if the
    Patient's Primary Owner changes later; changing the Hospitalisation owner
    itself is validated against the Patient's current Primary Owner.
    """
    consultation = None
    if doc.get("linked_consultation"):
        consultation = _consultation_context(doc.get("linked_consultation"))
        _require_same(_("Patient"), doc.get("patient"), consultation.get("patient"))
        _require_same(_("Pet Owner"), doc.get("customer"), consultation.get("primary_owner"))
        _require_same(_("Service Branch"), doc.get("service_branch"), consultation.get("service_branch"))
        _require_same(_("Company"), doc.get("company"), consultation.get("company"))
        _set_if_missing(doc, "patient", consultation.get("patient"))
        _set_if_missing(doc, "customer", consultation.get("primary_owner"))
        _set_if_missing(doc, "service_branch", consultation.get("service_branch"))
        _set_if_missing(doc, "company", consultation.get("company"))
        _set_if_missing(doc, "attending_veterinarian", consultation.get("consulting_practitioner"))

    patient_name = _clean(doc.get("patient"))
    if not patient_name:
        frappe.throw(_("Patient is required for Veterinary Hospitalisation."), frappe.ValidationError)

    patient = _patient_context(patient_name)
    patient_owner = _clean(patient.get("primary_owner"))
    previous = _previous_doc(doc)

    if consultation:
        if _clean(consultation.get("patient")) != patient_name:
            frappe.throw(_("Linked Consultation must belong to the selected Veterinary Patient."), frappe.ValidationError)
        # The Consultation preserves the owner for that clinical episode. Do not
        # rewrite or invalidate historical Hospitalisations when Patient ownership
        # changes after the Consultation was created.
        if not _clean(doc.get("customer")):
            doc.set("customer", consultation.get("primary_owner"))
    else:
        _set_if_missing(doc, "customer", patient_owner)
        _set_if_missing(doc, "service_branch", patient.get("default_branch"))
        if not _is_unchanged_historical_owner(doc, previous, patient_name):
            if _clean(doc.get("customer")) != patient_owner:
                frappe.throw(
                    _("Hospitalisation Pet Owner must match the selected Patient's current Primary Owner."),
                    frappe.ValidationError,
                )

    if not _clean(doc.get("service_branch")):
        frappe.throw(_("Service Branch is required for Veterinary Hospitalisation."), frappe.ValidationError)
