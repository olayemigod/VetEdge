from __future__ import annotations

import frappe
from frappe import _

from vetedge.services.portal_access import require_internal_user


def _align_grooming_detail(detail: dict, session_name: str) -> dict:
    from vetedge.services.grooming_payment_workflow import (
        get_grooming_cancellation_state,
        get_grooming_service_payment_gate_state,
    )

    doc = frappe.get_doc("Pet Grooming Session", session_name)
    gate = get_grooming_service_payment_gate_state(doc)
    cancellation = get_grooming_cancellation_state(doc)
    detail["payment_gate"] = gate
    detail["cancellation"] = cancellation

    blocked_keys = set()
    if not gate.get("can_proceed"):
        blocked_keys.update({"start-grooming", "complete-grooming"})
    if not cancellation.get("can_cancel"):
        blocked_keys.add("cancel-grooming")

    actions = [action for action in detail.get("actions") or [] if action.get("key") not in blocked_keys]

    veterinary_appointment = doc.get("veterinary_appointment")
    legacy_appointment = doc.get("appointment")
    actions = [action for action in actions if action.get("key") != "open-grooming-appointment"]
    if veterinary_appointment:
        detail.setdefault("fields", []).append(
            {
                "key": "veterinary_appointment",
                "label": _("Veterinary Appointment"),
                "type": "Link",
                "value": veterinary_appointment,
            }
        )
        actions.insert(
            0,
            {
                "key": "open-veterinary-appointment",
                "label": _("Open Appointment"),
                "target_name": veterinary_appointment,
            },
        )
    elif legacy_appointment:
        actions.insert(
            0,
            {
                "key": "open-legacy-grooming-appointment",
                "label": _("Open Legacy Appointment"),
                "target_name": legacy_appointment,
            },
        )

    if not gate.get("can_proceed"):
        billing = next((action for action in actions if action.get("key") == "billing"), None)
        if billing:
            billing["label"] = _("Billing / Payment Required")
            billing["primary"] = True
        detail["workflow_message"] = gate.get("message")
    if not cancellation.get("can_cancel"):
        detail["cancellation_message"] = cancellation.get("message")

    detail["actions"] = actions
    return detail


@frappe.whitelist()
def get_service_operation_detail(resource: str, name: str) -> dict:
    require_internal_user()
    from vetedge.services.service_operations import get_service_operation_detail as original

    detail = original(resource=resource, name=name)
    if resource == "grooming-sessions":
        return _align_grooming_detail(detail, name)
    return detail


@frappe.whitelist()
def transition_grooming_session(session: str, status: str) -> dict:
    require_internal_user()
    from vetedge.services.grooming import transition_grooming_session_status
    from vetedge.services.platform_access import require_vetedge_platform_access

    require_vetedge_platform_access(
        action="service_operations_transition_grooming_session",
        reference_doctype="Pet Grooming Session",
        reference_name=session,
    )
    transition_grooming_session_status(session, status)
    return get_service_operation_detail("grooming-sessions", session)
