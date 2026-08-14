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


def _lab_actions(name: str) -> dict[str, Any]:
    from vetedge.services.lab import LAB_ORDER_DOCTYPE, VALID_LAB_ORDER_STATUS_TRANSITIONS
    from vetedge.services.permissions import can_access_lab_order

    can_access_lab_order(frappe.session.user, name, raise_exception=True)
    doc = frappe.get_doc(LAB_ORDER_DOCTYPE, name)
    if not frappe.has_permission(LAB_ORDER_DOCTYPE, "write", doc=doc):
        return {"status": doc.status, "actions": []}

    actions = []
    valid_targets = VALID_LAB_ORDER_STATUS_TRANSITIONS.get(doc.status, set())
    for label, target, primary, danger in LAB_ACTIONS.get(doc.status, []):
        if target not in valid_targets or not _lab_target_permitted(doc, target):
            continue
        confirm = ""
        if target == "Cancelled":
            confirm = _(
                "Cancel this Lab Order? Billing cleanup follows the existing billing-session rules; submitted invoices are never silently mutated."
            )
        elif target == "Completed":
            confirm = _(
                "Complete this Lab Order? The server will verify result-review requirements and the configured payment gate first."
            )
        actions.append(
            {
                "label": _(label),
                "method": "vetedge.services.lab.transition_lab_order_status",
                "args": {"lab_order": doc.name, "status": target},
                "target_status": target,
                "primary": primary,
                "danger": danger,
                "confirm": confirm,
            }
        )
    return {
        "status": doc.status,
        "actions": actions,
        "message": _(
            "Lab workflow actions are permission-aware. Result entry, review, billing and completion gates are revalidated by the server when an action runs."
        ),
    }


def _vaccination_actions(name: str) -> dict[str, Any]:
    from vetedge.services.permissions import can_access_branch_data
    from vetedge.services.vaccination import (
        VACCINATION_RECORD_DOCTYPE,
        can_administer_vaccine,
    )

    doc = frappe.get_doc(VACCINATION_RECORD_DOCTYPE, name)
    if not frappe.has_permission(VACCINATION_RECORD_DOCTYPE, "read", doc=doc):
        frappe.throw(_("You do not have permission to view this vaccination record."), frappe.PermissionError)
    can_access_branch_data(frappe.session.user, doc.get("service_branch"), raise_exception=True)

    actions = []
    if doc.status in {"Draft", "Awaiting Payment", "Pending Administration"} and can_administer_vaccine(
        frappe.session.user,
        doc,
        raise_exception=False,
    ):
        actions.append(
            {
                "label": _("Administer Vaccination"),
                "method": "vetedge.services.vaccination.administer_vaccination",
                "args": {"record": doc.name},
                "target_status": "Administered",
                "primary": True,
                "danger": False,
                "confirm": _(
                    "Administer this vaccination? The server will enforce payment policy, role/branch access, vaccine stock availability, batch/expiry rules and stock posting before completion."
                ),
            }
        )
    return {
        "status": doc.status,
        "actions": actions,
        "message": _(
            "Vaccination administration is a controlled server action. Payment and stock gates are checked again when it runs."
        ),
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
    return {"status": None, "actions": [], "message": ""}
