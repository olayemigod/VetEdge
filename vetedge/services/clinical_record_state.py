from __future__ import annotations

import frappe
from frappe.utils import cint, flt

from vetedge.services.clinical_consultation_context import decorate_consultation_link_field
from vetedge.services.portal_access import require_internal_user


LAB_REDUNDANT_FIELDNAMES = {"status"}
LAB_HIDE_WHEN_EMPTY_READ_ONLY = {"consultation", "doctor_reviewed_by", "doctor_reviewed_on", "linked_invoice"}
LAB_SAFE_AFTER_SUBMITTED_INVOICE = {"sample_notes"}


def _lab_gate(lab_order: str) -> dict:
    from vetedge.services.lab_payment_workflow import get_lab_service_payment_gate_state

    doc = frappe.get_doc("Veterinary Lab Order", lab_order)
    return get_lab_service_payment_gate_state(doc)


def _normalize_datetime_value(field: dict) -> None:
    if field.get("fieldtype") != "Datetime" or not field.get("value"):
        return
    value = str(field.get("value"))
    if " " in value and "T" not in value:
        value = value.replace(" ", "T", 1)
    field["value"] = value[:16]


def _simplify_lab_fields(state: dict) -> None:
    fields = []
    for field in state.get("fields") or []:
        _normalize_datetime_value(field)
        fieldname = field.get("fieldname")
        if fieldname in LAB_REDUNDANT_FIELDNAMES:
            continue
        if (
            fieldname in LAB_HIDE_WHEN_EMPTY_READ_ONLY
            and field.get("read_only")
            and field.get("value") in (None, "")
        ):
            continue
        fields.append(field)
    state["fields"] = fields


def _apply_lab_billing_evidence(state: dict, gate: dict) -> None:
    row_billing = gate.get("row_billing") or {}
    evidence_rows = list(row_billing.values())
    active_evidence = [row for row in evidence_rows if cint(row.get("docstatus")) in {0, 1}]
    has_submitted = any(cint(row.get("docstatus")) == 1 for row in active_evidence)
    has_draft = any(cint(row.get("docstatus")) == 0 for row in active_evidence)
    submitted_rows = [row for row in active_evidence if cint(row.get("docstatus")) == 1]
    is_paid = bool(submitted_rows) and all(flt(row.get("outstanding_amount")) <= 0 for row in submitted_rows)

    billing_state = state.setdefault("billing_state", {})
    if active_evidence:
        billing_state["has_invoice"] = True
        billing_state["has_draft_invoice"] = has_draft
        billing_state["has_submitted_invoice"] = has_submitted
        billing_state["is_paid"] = is_paid and not has_draft
        billing_state["locked"] = has_submitted

    if has_submitted:
        for field in state.get("fields") or []:
            if field.get("fieldname") not in LAB_SAFE_AFTER_SUBMITTED_INVOICE:
                field["read_only"] = 1
        state["can_save"] = bool(
            state.get("can_save")
            and any(not field.get("read_only") for field in state.get("fields") or [])
        )

    for section in state.get("sections") or []:
        if section.get("kind") != "lab_results":
            continue
        for row in section.get("rows") or []:
            evidence = row_billing.get(str(row.get("name") or ""))
            if not evidence:
                continue
            row["billing_status"] = evidence.get("billing_status") or row.get("billing_status") or "Not Billed"
            row["billing_invoice"] = evidence.get("invoice")
            if cint(evidence.get("docstatus")) == 1:
                row["can_edit_rate"] = False


def _apply_gate_to_lab_sections(state: dict, gate: dict) -> None:
    if gate.get("can_proceed"):
        return
    for section in state.get("sections") or []:
        if section.get("kind") != "lab_results":
            continue
        section["message"] = gate.get("message") or section.get("message")
        for row in section.get("rows") or []:
            row["can_edit_result"] = False


def _merge_gate_message(state: dict, gate: dict) -> None:
    if gate.get("can_proceed"):
        return
    billing_state = state.setdefault("billing_state", {})
    existing = str(billing_state.get("message") or "").strip()
    blocker = str(gate.get("message") or "").strip()
    billing_state["service_gate_blocked"] = True
    billing_state["service_gate"] = gate
    billing_state["message"] = " ".join(part for part in (blocker, existing) if part)


@frappe.whitelist()
def get_clinical_record_editor(doctype: str, name: str) -> dict:
    require_internal_user()
    from vetedge.services.clinical_record_editor import get_clinical_record_editor as original

    state = original(doctype=doctype, name=name)
    if doctype != "Veterinary Lab Order":
        return state
    state = decorate_consultation_link_field(state, doctype, name)
    _simplify_lab_fields(state)
    gate = _lab_gate(name)
    state["service_gate"] = gate
    _apply_lab_billing_evidence(state, gate)
    _apply_gate_to_lab_sections(state, gate)
    _merge_gate_message(state, gate)
    return state


@frappe.whitelist()
def get_lab_result_editor(lab_order: str, row_name: str) -> dict:
    require_internal_user()
    from vetedge.services.clinical_record_editor import get_lab_result_editor as original

    state = original(lab_order=lab_order, row_name=row_name)
    gate = _lab_gate(lab_order)
    state["service_gate"] = gate
    if gate.get("can_proceed"):
        return state

    state["can_save"] = False
    state["can_upload"] = False
    state["gate_message"] = gate.get("message")
    for field in state.get("fields") or []:
        field["read_only"] = 1
    return state
