from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from vetedge.services.portal_access import require_internal_user


LAB_ACTIONS: dict[str, list[tuple[str, str, bool, bool]]] = {
    "Draft": [("Order Lab Tests", "Ordered", True, False)],
    "Ordered": [
        ("Mark Sample Collected", "Sample Collected", True, False),
        ("Send to Lab", "Sent to Lab", False, False),
        ("Start Processing", "In Progress", False, False),
        ("Cancel Lab Order", "Cancelled", False, True),
    ],
    "Sample Collected": [
        ("Send to Lab", "Sent to Lab", True, False),
        ("Start Processing", "In Progress", False, False),
        ("Cancel Lab Order", "Cancelled", False, True),
    ],
    "Sent to Lab": [
        ("Start Processing", "In Progress", True, False),
        ("Mark Result Pending", "Result Pending", False, False),
        ("Cancel Lab Order", "Cancelled", False, True),
    ],
    "In Progress": [
        ("Mark Result Pending", "Result Pending", True, False),
        ("Cancel Lab Order", "Cancelled", False, True),
    ],
    "Result Pending": [("Cancel Lab Order", "Cancelled", False, True)],
    "Result Entered": [
        ("Mark Reviewed", "Reviewed", True, False),
        ("Complete Lab Order", "Completed", False, False),
        ("Cancel Lab Order", "Cancelled", False, True),
    ],
    "Awaiting Review": [
        ("Mark Reviewed", "Reviewed", True, False),
        ("Cancel Lab Order", "Cancelled", False, True),
    ],
    "Reviewed": [
        ("Complete Lab Order", "Completed", True, False),
        ("Cancel Lab Order", "Cancelled", False, True),
    ],
}


def _lab_target_permitted(doc, target: str) -> bool:
    from vetedge.services.lab import LAB_RESULT_ENTRY_STATUSES
    from vetedge.services.permissions import (
        can_enter_lab_results,
        can_request_lab_tests,
        can_review_lab_results,
    )

    user = frappe.session.user
    if target == "Ordered":
        return can_request_lab_tests(user, doc, raise_exception=False)
    if target in LAB_RESULT_ENTRY_STATUSES:
        return can_enter_lab_results(user, doc, raise_exception=False)
    if target == "Reviewed":
        return can_review_lab_results(user, doc, raise_exception=False)
    if target == "Cancelled":
        return bool(
            can_enter_lab_results(user, doc, raise_exception=False)
            or can_review_lab_results(user, doc, raise_exception=False)
        )
    return True


def _active_lab_rows(doc) -> list:
    return [row for row in doc.get("lab_tests") or [] if row.get("status") != "Cancelled"]


def _lab_review_is_required_and_pending(doc) -> bool:
    return any(
        bool(row.get("requires_result_review")) and row.get("result_status") != "Reviewed"
        for row in _active_lab_rows(doc)
    )


def _lab_payment_gate(doc) -> tuple[bool, str, dict]:
    from vetedge.services.lab_payment_workflow import get_lab_service_payment_gate_state

    state = get_lab_service_payment_gate_state(doc)
    return bool(state.get("can_proceed")), str(state.get("message") or ""), state


def _lab_completion_gate(doc) -> tuple[bool, str, dict]:
    if _lab_review_is_required_and_pending(doc):
        return False, _("Review all required Lab Test results before completing this Lab Order."), {}
    return _lab_payment_gate(doc)


def _lab_actions(name: str) -> dict[str, Any]:
    from vetedge.services.lab import LAB_ORDER_DOCTYPE, VALID_LAB_ORDER_STATUS_TRANSITIONS
    from vetedge.services.lab_payment_workflow import SERVICE_PROGRESS_STATUSES
    from vetedge.services.permissions import can_access_lab_order

    can_access_lab_order(frappe.session.user, name, raise_exception=True)
    doc = frappe.get_doc(LAB_ORDER_DOCTYPE, name)
    if not frappe.has_permission(LAB_ORDER_DOCTYPE, "write", doc=doc):
        return {
            "status": doc.status,
            "actions": [],
            "message": _("This Lab Order is read-only for your current permissions."),
            "billing_required": False,
        }

    actions = []
    blockers: list[str] = []
    payment_state: dict = {}
    billing_required = False
    valid_targets = VALID_LAB_ORDER_STATUS_TRANSITIONS.get(doc.status, set())

    for label, target, primary, danger in LAB_ACTIONS.get(doc.status, []):
        if target not in valid_targets or not _lab_target_permitted(doc, target):
            continue

        if target in SERVICE_PROGRESS_STATUSES:
            if target == "Completed":
                ready, reason, gate = _lab_completion_gate(doc)
            else:
                ready, reason, gate = _lab_payment_gate(doc)
            if gate:
                payment_state = gate
            if not ready:
                billing_required = bool(gate and not gate.get("can_proceed"))
                if reason and reason not in blockers:
                    blockers.append(reason)
                continue

        confirm = ""
        method = "vetedge.services.lab.transition_lab_order_status"
        args = {"lab_order": doc.name, "status": target}
        if target == "Reviewed":
            method = "vetedge.services.lab_workflow_actions.review_lab_order_results"
            args = {"lab_order": doc.name}
            confirm = _(
                "Mark all active Lab Test results as reviewed? Reviewer identity and timestamp will be recorded by the server."
            )
        elif target == "Cancelled":
            confirm = _(
                "Cancel this Lab Order? Billing cleanup follows the existing billing-session rules; submitted invoices are never silently mutated."
            )
        elif target == "Completed":
            confirm = _(
                "Complete this Lab Order? Result-review requirements and the configured payment gate have passed preflight and will be revalidated by the server."
            )
        actions.append(
            {
                "label": _(label),
                "method": method,
                "args": args,
                "target_status": target,
                "primary": primary,
                "danger": danger,
                "confirm": confirm,
            }
        )

    message_parts = [
        _(
            "Lab workflow is server-controlled. Ordering may be recorded before payment, but sample collection, processing, result entry, review and completion require the configured Billing & Payment gate."
        )
    ]
    message_parts.extend(blockers)
    return {
        "status": doc.status,
        "actions": actions,
        "message": " ".join(part for part in message_parts if part),
        "billing_required": billing_required,
        "payment_gate": payment_state,
    }


def _vaccination_actions(name: str) -> dict[str, Any]:
    from vetedge.services.permissions import can_access_branch_data
    from vetedge.services.vaccination import VACCINATION_RECORD_DOCTYPE, can_administer_vaccine
    from vetedge.services.vaccination_payment_workflow import get_vaccination_administration_gate_state

    doc = frappe.get_doc(VACCINATION_RECORD_DOCTYPE, name)
    if not frappe.has_permission(VACCINATION_RECORD_DOCTYPE, "read", doc=doc):
        frappe.throw(_("You do not have permission to view this vaccination record."), frappe.PermissionError)
    can_access_branch_data(frappe.session.user, doc.get("service_branch"), raise_exception=True)

    actions = []
    billing_required = False
    payment_state: dict = {}
    message = _(
        "Vaccination administration is a controlled server action. Payment, role/branch and stock gates are rechecked when it runs."
    )
    if doc.status in {"Draft", "Awaiting Payment", "Pending Administration"} and can_administer_vaccine(
        frappe.session.user,
        doc,
        raise_exception=False,
    ):
        payment_state = dict(get_vaccination_administration_gate_state(doc) or {})
        payment_ready = bool(payment_state.get("can_proceed"))
        payment_message = str(payment_state.get("message") or "")
        if payment_ready:
            actions.append(
                {
                    "label": _("Administer Vaccination"),
                    "method": "vetedge.services.vaccination.administer_vaccination",
                    "args": {"record": doc.name},
                    "target_status": "Administered",
                    "primary": True,
                    "danger": False,
                    "confirm": _(
                        "Administer this vaccination? The server will recheck payment policy, role/branch access, vaccine stock availability, batch/expiry rules and stock posting before completion."
                    ),
                }
            )
        else:
            billing_required = True
            if payment_message:
                message = f"{message} {payment_message}"
    return {
        "status": doc.status,
        "actions": actions,
        "message": message,
        "billing_required": billing_required,
        "payment_gate": payment_state,
    }


@frappe.whitelist()
def get_clinical_workflow_actions(doctype: str, name: str) -> dict[str, Any]:
    require_internal_user()
    if not name or not frappe.db.exists(doctype, name):
        frappe.throw(_("The selected clinical record could not be found."), frappe.DoesNotExistError)
    if doctype == "Veterinary Lab Order":
        return _lab_actions(name)
    if doctype == "Veterinary Vaccination Record":
        return _vaccination_actions(name)
    return {"status": None, "actions": [], "message": "", "billing_required": False}
