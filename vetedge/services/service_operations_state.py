from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cstr

from vetedge.services.portal_access import require_internal_user


EDITABLE_GROOMING_SESSION_STATUSES = {"Draft", "Awaiting Payment", "Pending Grooming", "In Progress"}
GROOMING_EXECUTION_FIELDS = {"pre_grooming_notes", "post_grooming_notes"}


def _grooming_workflow_state(doc, gate: dict) -> dict:
    status = str(doc.get("status") or "Draft")
    if status == "Completed":
        return {
            "stage": _("Completed"),
            "message": _("Grooming is complete. The session is now read-only; open the Appointment for scheduling history or Billing / Payment for financial history."),
        }
    if status == "Cancelled":
        return {
            "stage": _("Cancelled"),
            "message": _("This Grooming Session is cancelled and read-only."),
        }
    if status == "In Progress":
        return {
            "stage": _("Grooming In Progress"),
            "message": _("Update the session notes, then complete Grooming when the service is finished."),
        }
    if gate.get("billable") and not gate.get("can_proceed"):
        return {
            "stage": _("Billing / Payment Required"),
            "message": gate.get("message") or _("Complete Grooming Billing / Payment before starting the service."),
        }
    return {
        "stage": _("Ready to Start"),
        "message": _("Review the pre-grooming notes, then start Grooming. Session notes remain editable until completion."),
    }


def _grooming_edit_state(doc) -> dict:
    can_edit = bool(doc.has_permission("write") and doc.get("status") in EDITABLE_GROOMING_SESSION_STATUSES)
    return {
        "can_edit": can_edit,
        "editable_fields": sorted(GROOMING_EXECUTION_FIELDS) if can_edit else [],
        "message": (
            _("Edit execution notes here. Patient, branch, Grooming Service and scheduled Groomer remain controlled by the Appointment.")
            if can_edit
            else _("Completed and cancelled Grooming Sessions are read-only.")
        ),
    }


def _align_grooming_detail(detail: dict, session_name: str) -> dict:
    from vetedge.services.grooming_payment_workflow import (
        get_grooming_cancellation_state,
        get_grooming_service_payment_gate_state,
    )

    doc = frappe.get_doc("Pet Grooming Session", session_name)
    gate = get_grooming_service_payment_gate_state(doc)
    cancellation = get_grooming_cancellation_state(doc)
    edit_state = _grooming_edit_state(doc)
    detail["payment_gate"] = gate
    detail["cancellation"] = cancellation
    detail["edit_state"] = edit_state
    detail["workflow_state"] = _grooming_workflow_state(doc, gate)

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

    if edit_state.get("can_edit"):
        insert_at = 1 if actions and actions[0].get("key") in {"open-veterinary-appointment", "open-legacy-grooming-appointment"} else 0
        actions.insert(insert_at, {"key": "edit-grooming-session", "label": _("Edit Session")})

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
def save_grooming_session_execution(
    session: str,
    values: dict | str | None = None,
    expected_modified: str | None = None,
) -> dict:
    """Save execution notes without changing scheduling, billing or workflow truth."""
    require_internal_user()
    from vetedge.services.permissions import can_access_branch_data, get_current_user
    from vetedge.services.platform_access import require_vetedge_platform_access

    require_vetedge_platform_access(
        action="save_grooming_session_execution",
        reference_doctype="Pet Grooming Session",
        reference_name=session,
    )
    doc = frappe.get_doc("Pet Grooming Session", session)
    doc.check_permission("write")
    if doc.get("service_branch"):
        can_access_branch_data(get_current_user(), doc.service_branch, raise_exception=True)
    if doc.get("status") not in EDITABLE_GROOMING_SESSION_STATUSES:
        frappe.throw(_("Completed and cancelled Grooming Sessions are read-only."), frappe.ValidationError)
    if expected_modified and cstr(doc.modified) != cstr(expected_modified):
        frappe.throw(
            _("This Grooming Session was updated after you opened it. Refresh the session and try again."),
            frappe.TimestampMismatchError,
        )

    payload = frappe.parse_json(values or {})
    if not isinstance(payload, dict):
        frappe.throw(_("Grooming Session values must be a JSON object."), frappe.ValidationError)
    unsupported = sorted(set(payload) - GROOMING_EXECUTION_FIELDS)
    if unsupported:
        frappe.throw(
            _("These Grooming Session fields cannot be edited here: {0}").format(", ".join(unsupported)),
            frappe.ValidationError,
        )

    for fieldname in GROOMING_EXECUTION_FIELDS:
        if fieldname in payload:
            doc.set(fieldname, payload.get(fieldname) or None)
    doc.save()
    return get_service_operation_detail("grooming-sessions", doc.name)


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
