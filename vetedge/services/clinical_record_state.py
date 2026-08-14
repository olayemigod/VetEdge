from __future__ import annotations

import frappe

from vetedge.services.portal_access import require_internal_user


def _lab_gate(lab_order: str) -> dict:
    from vetedge.services.lab_payment_workflow import get_lab_service_payment_gate_state

    doc = frappe.get_doc("Veterinary Lab Order", lab_order)
    return get_lab_service_payment_gate_state(doc)


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
    gate = _lab_gate(name)
    state["service_gate"] = gate
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
