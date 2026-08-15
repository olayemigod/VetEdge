from __future__ import annotations

from typing import Any

import frappe

from vetedge.services.platform_access import require_vetedge_platform_access
from vetedge.services.portal_access import require_internal_user


VACCINATION_PROTECTED_EDITOR_FIELDS = {
    "linked_consultation",
    "administered_by",
    "administered_on",
    "next_vaccination_appointment",
    "batch_no",
    "expiry_date",
    "billing_item",
    "amount",
    "linked_invoice",
    "stock_entry_reference",
}


def _gate(action: str, doctype: str | None = None, name: str | None = None) -> None:
    require_internal_user()
    require_vetedge_platform_access(
        action=action,
        reference_doctype=doctype,
        reference_name=name,
    )


def _parse_values(values: str | dict | None) -> dict[str, Any]:
    if not values:
        return {}
    if isinstance(values, dict):
        return dict(values)
    parsed = frappe.parse_json(values)
    return dict(parsed) if isinstance(parsed, dict) else {}


@frappe.whitelist()
def create_clinical_record(doctype: str, values=None):
    _gate("create_clinical_record", doctype)
    from vetedge.services.clinical_record_editor import create_clinical_record as original

    return original(doctype=doctype, values=values)


@frappe.whitelist()
def save_clinical_record_editor(doctype: str, name: str, values=None):
    _gate("save_clinical_record_editor", doctype, name)
    payload = _parse_values(values)
    if doctype == "Veterinary Vaccination Record":
        # These fields are set by administration, inventory, scheduling and
        # billing authorities. A crafted API request must not be able to mutate
        # them merely because an older editor schema once exposed them.
        for fieldname in VACCINATION_PROTECTED_EDITOR_FIELDS:
            payload.pop(fieldname, None)
    from vetedge.services.clinical_record_editor import save_clinical_record_editor as original

    return original(doctype=doctype, name=name, values=payload)


@frappe.whitelist()
def delete_clinical_record(doctype: str, name: str):
    _gate("delete_clinical_record", doctype, name)
    from vetedge.services.clinical_record_editor import delete_clinical_record as original

    return original(doctype=doctype, name=name)


@frappe.whitelist()
def save_lab_result_editor(lab_order: str, row_name: str, values=None):
    _gate("save_lab_result_editor", "Veterinary Lab Order", lab_order)
    from vetedge.services.clinical_record_editor import save_lab_result_editor as original

    return original(lab_order=lab_order, row_name=row_name, values=values)


@frappe.whitelist()
def save_lab_test_rate(lab_order: str, row_name: str, rate):
    _gate("save_lab_test_rate", "Veterinary Lab Order", lab_order)
    from vetedge.services.clinical_record_editor import save_lab_test_rate as original

    return original(lab_order=lab_order, row_name=row_name, rate=rate)


@frappe.whitelist()
def transition_lab_order_status(lab_order: str, status: str):
    _gate("transition_lab_order_status", "Veterinary Lab Order", lab_order)
    from vetedge.services.lab import transition_lab_order_status as original

    return original(lab_order=lab_order, status=status)


@frappe.whitelist()
def create_manual_registration_invoice(patient: str):
    _gate("create_manual_registration_invoice", "Veterinary Patient", patient)
    from vetedge.services.permissions import can_access_patient

    can_access_patient(frappe.session.user, patient, raise_exception=True)
    patient_doc = frappe.get_doc("Veterinary Patient", patient)
    from vetedge.services.permissions import can_access_branch_data

    can_access_branch_data(frappe.session.user, patient_doc.get("default_branch"), raise_exception=True)
    from vetedge.services.registration_billing import create_manual_registration_invoice as original

    return original(patient=patient)
