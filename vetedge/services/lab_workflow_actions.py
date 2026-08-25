from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import now_datetime

from vetedge.services.platform_access import require_vetedge_platform_access
from vetedge.services.portal_access import require_internal_user


@frappe.whitelist()
def review_lab_order_results(lab_order: str) -> dict:
    require_internal_user()
    from vetedge.services.lab import LAB_ORDER_DOCTYPE
    from vetedge.services.permissions import can_access_lab_order, can_review_lab_results

    can_access_lab_order(frappe.session.user, lab_order, raise_exception=True)
    doc = frappe.get_doc(LAB_ORDER_DOCTYPE, lab_order)
    can_review_lab_results(frappe.session.user, doc, raise_exception=True)
    require_vetedge_platform_access(
        action="review_lab_order_results",
        reference_doctype=LAB_ORDER_DOCTYPE,
        reference_name=lab_order,
    )

    if doc.status not in {"Result Entered", "Awaiting Review", "Reviewed"}:
        frappe.throw(
            _("Lab results can be reviewed only after results have been entered."),
            frappe.ValidationError,
        )

    active_rows = [row for row in doc.get("lab_tests") or [] if row.get("status") != "Cancelled"]
    if not active_rows:
        frappe.throw(_("This Lab Order has no active Lab Tests to review."), frappe.ValidationError)

    missing = []
    for row in active_rows:
        has_result = any(
            row.get(fieldname) not in (None, "")
            for fieldname in ("result_value", "result_text", "result_attachment")
        )
        if not has_result:
            missing.append(row.get("lab_test_name") or row.get("lab_test_template") or row.name)
    if missing:
        frappe.throw(
            _("Enter results for all active Lab Tests before review: {0}").format(", ".join(missing)),
            frappe.ValidationError,
        )

    for row in active_rows:
        row.result_status = "Reviewed"
        row.status = "Reviewed"
    doc.status = "Reviewed"
    doc.doctor_reviewed_by = frappe.session.user
    doc.doctor_reviewed_on = now_datetime()
    doc.save()

    return {
        "name": doc.name,
        "status": doc.status,
        "doctor_reviewed_by": doc.doctor_reviewed_by,
        "doctor_reviewed_on": doc.doctor_reviewed_on,
    }
