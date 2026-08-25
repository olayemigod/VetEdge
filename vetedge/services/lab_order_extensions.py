from __future__ import annotations

import frappe
from frappe import _

from vetedge.services.patient_service_guard import assert_patient_accepts_new_service
from vetedge.services.platform_access import require_vetedge_platform_access
from vetedge.services.portal_access import require_internal_user


EDITABLE_TEST_STATUSES = {"Draft", "Ordered"}


def _get_doc(lab_order: str):
    if not lab_order or not frappe.db.exists("Veterinary Lab Order", lab_order):
        frappe.throw(_("The selected Lab Order could not be found."), frappe.DoesNotExistError)
    doc = frappe.get_doc("Veterinary Lab Order", lab_order)
    doc.check_permission("write")
    return doc


def _assert_addable(doc) -> None:
    require_vetedge_platform_access(
        action="add_lab_tests",
        reference_doctype="Veterinary Lab Order",
        reference_name=doc.name,
    )
    if doc.docstatus != 0 or str(doc.get("status") or "Draft") not in EDITABLE_TEST_STATUSES:
        frappe.throw(
            _("Lab Tests can only be added while the Lab Order is Draft or Ordered."),
            frappe.ValidationError,
        )
    from vetedge.services.permissions import can_request_lab_tests

    can_request_lab_tests(frappe.session.user, doc, raise_exception=True)
    assert_patient_accepts_new_service(doc.get("patient"), _("laboratory test"))

    from vetedge.services.clinical_record_editor import _billing_edit_state, _config

    billing = _billing_edit_state(doc, _config("Veterinary Lab Order"))
    if billing.get("has_submitted_invoice"):
        frappe.throw(
            _("Lab Tests cannot be added after a linked invoice has been submitted."),
            frappe.ValidationError,
        )


@frappe.whitelist()
def get_addable_lab_tests(lab_order: str, txt: str = "") -> list[dict]:
    require_internal_user()
    doc = _get_doc(lab_order)
    _assert_addable(doc)
    existing = {str(row.get("lab_test_template") or "") for row in doc.get("lab_tests") or []}

    from vetedge.services.lab import get_active_lab_tests_for_picker

    query = str(txt or "").strip().lower()
    options = []
    for row in get_active_lab_tests_for_picker() or []:
        name = str(row.get("name") or "")
        label = str(row.get("test_name") or name)
        if not name or name in existing:
            continue
        searchable = " ".join(
            str(row.get(key) or "")
            for key in ("name", "test_name", "sample_type", "result_format")
        ).lower()
        if query and query not in searchable:
            continue
        options.append(
            {
                "value": name,
                "label": label,
                "description": " · ".join(
                    filter(None, [str(row.get("sample_type") or ""), str(row.get("result_format") or "")])
                ),
                "rate": row.get("default_rate") or 0,
                "result_format": row.get("result_format") or "Value Driven",
            }
        )
    return options[:50]


@frappe.whitelist()
def add_lab_tests(lab_order: str, lab_tests: str | list | None = None) -> dict:
    require_internal_user()
    doc = _get_doc(lab_order)
    _assert_addable(doc)
    selected = lab_tests if isinstance(lab_tests, list) else frappe.parse_json(lab_tests or "[]")
    if not isinstance(selected, list):
        frappe.throw(_("Expected a list of Lab Tests."), frappe.ValidationError)
    selected = list(dict.fromkeys(str(value or "").strip() for value in selected if str(value or "").strip()))
    if not selected:
        frappe.throw(_("Select at least one Lab Test."), frappe.ValidationError)

    active = {row["value"] for row in get_addable_lab_tests(lab_order)}
    invalid = [name for name in selected if name not in active]
    if invalid:
        frappe.throw(
            _("These Lab Tests are unavailable or already present: {0}").format(", ".join(invalid)),
            frappe.ValidationError,
        )

    for lab_test in selected:
        doc.append("lab_tests", {"lab_test_template": lab_test})
    doc.save()

    from vetedge.services.clinical_record_editor import _billing_edit_state, _config

    billing = _billing_edit_state(doc, _config("Veterinary Lab Order"))
    if billing.get("has_draft_invoice"):
        from vetedge.services.billing_modal import create_or_update_modal_invoice

        create_or_update_modal_invoice("Veterinary Lab Order", doc.name)

    return {"name": doc.name, "added": selected}
