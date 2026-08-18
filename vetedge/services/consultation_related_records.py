from __future__ import annotations

from collections import defaultdict
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt


CONSULTATION_DOCTYPE = "Veterinary Consultation"
LAB_ORDER_DOCTYPE = "Veterinary Lab Order"
LAB_ORDER_ITEM_DOCTYPE = "Veterinary Lab Order Item"
LAB_TEST_DOCTYPE = "Veterinary Lab Test"
VACCINATION_DOCTYPE = "Veterinary Vaccination Record"
VACCINE_DOCTYPE = "Veterinary Vaccine"
SUPPORTED_RELATED_DOCTYPES = {LAB_ORDER_DOCTYPE, VACCINATION_DOCTYPE}
REMOVABLE_PLAN_BILLING_STATUSES = {"", "Pending", "Draft Invoiced", "Skipped", "Cancelled"}
REMOVABLE_PLAN_PAYMENT_STATUSES = {"", "Not Billed", "Unpaid", "Cancelled"}
FINAL_BILLING_STATUSES = {"Submitted Invoiced", "Paid"}
VACCINATION_EDIT_SETTING = "allow_vaccination_billing_edit_in_consultation"


def _parse_list(value) -> list:
    if value in (None, ""):
        return []
    parsed = frappe.parse_json(value) if isinstance(value, str) else value
    if isinstance(parsed, dict):
        return [parsed]
    return list(parsed or [])


def _require_consultation_access(consultation: str):
    from vetedge.services.permissions import can_access_consultation
    from vetedge.services.portal_access import require_internal_user

    require_internal_user()
    if not consultation or not frappe.db.exists(CONSULTATION_DOCTYPE, consultation):
        frappe.throw(_("The selected Veterinary Consultation could not be found."), frappe.DoesNotExistError)
    can_access_consultation(frappe.session.user, consultation, raise_exception=True)
    return frappe.get_doc(CONSULTATION_DOCTYPE, consultation)


def vaccination_billing_edit_is_enabled() -> bool:
    if not frappe.db.exists("DocType", "Veterinary Settings"):
        return True
    meta = frappe.get_meta("Veterinary Settings")
    if not meta.has_field(VACCINATION_EDIT_SETTING):
        return True
    return bool(cint(frappe.get_single("Veterinary Settings").get(VACCINATION_EDIT_SETTING)))


def consultation_source_billing_edit_policy() -> dict[str, bool]:
    return {
        "allow_editing_lab_billing": bool(frappe.has_permission(LAB_ORDER_DOCTYPE, "write")),
        "allow_editing_vaccination_billing": bool(
            vaccination_billing_edit_is_enabled()
            and frappe.has_permission(VACCINATION_DOCTYPE, "write")
        ),
    }


def apply_consultation_source_billing_edits(edits: list[dict[str, Any]] | None) -> None:
    for edit in edits or []:
        source_type = edit.get("source_type")
        if source_type == "Lab Order":
            _apply_lab_billing_edit(edit)
        elif source_type == "Vaccination":
            _apply_vaccination_billing_edit(edit)


def _assert_same_source_item(expected: str | None, supplied: str | None, label: str) -> None:
    if not expected:
        frappe.throw(
            _("{0} has no ERPNext Item. Configure its clinical master before editing the rate.").format(label),
            frappe.ValidationError,
        )
    if supplied and supplied != expected:
        frappe.throw(
            _("The ERPNext Item for {0} is controlled by its clinical master and cannot be changed from the Consultation.").format(label),
            frappe.ValidationError,
        )


def _apply_lab_billing_edit(edit: dict[str, Any]) -> None:
    name = edit.get("source_document")
    detail = edit.get("source_detail_name")
    if not name or not frappe.db.exists(LAB_ORDER_DOCTYPE, name):
        frappe.throw(_("The source Lab Order no longer exists."), frappe.DoesNotExistError)
    doc = frappe.get_doc(LAB_ORDER_DOCTYPE, name)
    doc.check_permission("write")
    target = None
    for row in doc.get("lab_tests") or []:
        if row.get("name") == detail or row.get("lab_test_template") == detail:
            target = row
            break
    if not target:
        frappe.throw(_("The source Lab Test row could not be found."), frappe.DoesNotExistError)
    _assert_same_source_item(
        target.get("billing_item"),
        edit.get("item"),
        target.get("lab_test_name") or target.get("lab_test_template") or _("Lab Test"),
    )
    target.rate = flt(edit.get("rate"))
    doc.save()


def _apply_vaccination_billing_edit(edit: dict[str, Any]) -> None:
    if not vaccination_billing_edit_is_enabled():
        frappe.throw(_("Vaccination rate edits from Consultation are disabled in Veterinary Settings."), frappe.PermissionError)
    name = edit.get("source_document")
    if not name or not frappe.db.exists(VACCINATION_DOCTYPE, name):
        frappe.throw(_("The source Vaccination Record no longer exists."), frappe.DoesNotExistError)
    doc = frappe.get_doc(VACCINATION_DOCTYPE, name)
    doc.check_permission("write")
    _assert_same_source_item(
        doc.get("billing_item"),
        edit.get("item"),
        doc.get("vaccine") or _("Vaccination"),
    )
    doc.rate = flt(edit.get("rate"))
    doc.rate_manually_edited = 1
    doc.save()


@frappe.whitelist()
def get_consultation_related_records(consultation: str, doctype: str) -> list[dict]:
    consultation_doc = _require_consultation_access(consultation)
    if doctype not in SUPPORTED_RELATED_DOCTYPES:
        frappe.throw(_("This related record type is not supported here."), frappe.ValidationError)
    if not frappe.has_permission(doctype, "read"):
        frappe.throw(_("You do not have permission to view {0}.").format(doctype), frappe.PermissionError)
    if doctype == LAB_ORDER_DOCTYPE:
        return _get_lab_rows(consultation_doc)
    return _get_vaccination_rows(consultation_doc)


def _get_lab_rows(consultation_doc) -> list[dict]:
    rows = frappe.get_list(
        LAB_ORDER_DOCTYPE,
        filters={"consultation": consultation_doc.name},
        fields=["name", "lab_order_title", "status", "requested_on", "requested_by", "linked_invoice"],
        order_by="requested_on desc, modified desc",
        limit_page_length=50,
    )
    names = [row.get("name") for row in rows if row.get("name")]
    children = (
        frappe.get_all(
            LAB_ORDER_ITEM_DOCTYPE,
            filters={"parent": ["in", names]},
            fields=[
                "parent",
                "name",
                "lab_test_name",
                "lab_test_template",
                "billing_item",
                "rate",
                "status",
                "result_value",
                "result_text",
                "result_attachment",
            ],
            order_by="parent asc, idx asc",
        )
        if names
        else []
    )
    by_parent: dict[str, list] = defaultdict(list)
    for child in children:
        by_parent[child.get("parent")].append(child)
    can_delete_role = bool(frappe.has_permission(LAB_ORDER_DOCTYPE, "delete"))
    result = []
    for row in rows:
        child_rows = by_parent.get(row.get("name"), [])
        tests = [child.get("lab_test_name") or child.get("lab_test_template") for child in child_rows]
        tests = [test for test in tests if test]
        has_result = any(
            child.get("result_value") not in (None, "")
            or child.get("result_text") not in (None, "")
            or child.get("result_attachment") not in (None, "")
            for child in child_rows
        )
        safe_state = row.get("status") in {"Draft", "Ordered"} and not has_result
        result.append(
            {
                **dict(row),
                "display_name": ", ".join(tests) or row.get("lab_order_title") or row.get("name"),
                "tests_summary": ", ".join(tests),
                "can_delete": bool(can_delete_role and safe_state and not consultation_doc.get("status") in {"Ready for Treatment", "Completed", "Cancelled"}),
                "delete_reason": "" if safe_state else _("Only Draft/Ordered Lab Orders without results can be deleted."),
            }
        )
    return result


def _get_vaccination_rows(consultation_doc) -> list[dict]:
    rows = frappe.get_list(
        VACCINATION_DOCTYPE,
        filters={"linked_consultation": consultation_doc.name},
        fields=[
            "name",
            "status",
            "vaccine",
            "administered_on",
            "next_due_date",
            "linked_invoice",
            "stock_entry_reference",
            "rate",
            "billing_item",
        ],
        order_by="creation desc",
        limit_page_length=50,
    )
    vaccine_names = list({row.get("vaccine") for row in rows if row.get("vaccine")})
    vaccine_map = {
        row.get("name"): row.get("vaccine_name") or row.get("name")
        for row in (
            frappe.get_all(VACCINE_DOCTYPE, filters={"name": ["in", vaccine_names]}, fields=["name", "vaccine_name"])
            if vaccine_names
            else []
        )
    }
    can_delete_role = bool(frappe.has_permission(VACCINATION_DOCTYPE, "delete"))
    result = []
    for row in rows:
        safe_state = row.get("status") in {"Draft", "Awaiting Payment", "Pending Administration"} and not row.get("stock_entry_reference")
        result.append(
            {
                **dict(row),
                "display_name": vaccine_map.get(row.get("vaccine"), row.get("vaccine")) or row.get("name"),
                "can_delete": bool(can_delete_role and safe_state and not consultation_doc.get("status") in {"Ready for Treatment", "Completed", "Cancelled"}),
                "delete_reason": "" if safe_state else _("Administered, cancelled or stock-posted vaccinations cannot be deleted."),
            }
        )
    return result


@frappe.whitelist()
def create_consultation_lab_order(
    consultation: str,
    lab_tests: list[dict] | str | None = None,
    sample_notes: str | None = None,
) -> dict:
    _require_consultation_access(consultation)
    rows = _parse_list(lab_tests)
    if not rows:
        frappe.throw(_("Select at least one Lab Test."), frappe.ValidationError)
    templates = [
        (row.get("lab_test_template") or row.get("name") or row.get("test")) if isinstance(row, dict) else row
        for row in rows
    ]
    templates = [str(value).strip() for value in templates if value]
    if len(templates) != len(set(templates)):
        frappe.throw(_("The same Lab Test cannot be added more than once."), frappe.ValidationError)

    from vetedge.services.lab import create_lab_order_from_consultation

    result = create_lab_order_from_consultation(
        consultation=consultation,
        lab_tests=[{"lab_test_template": value} for value in templates],
        sample_notes=sample_notes,
    )
    overrides = {
        str(row.get("lab_test_template") or row.get("name") or row.get("test")): row.get("rate")
        for row in rows
        if isinstance(row, dict)
        and (row.get("lab_test_template") or row.get("name") or row.get("test"))
        and row.get("rate") not in (None, "")
    }
    if overrides:
        doc = frappe.get_doc(LAB_ORDER_DOCTYPE, result.get("name"))
        for child in doc.get("lab_tests") or []:
            if child.get("lab_test_template") in overrides:
                child.rate = flt(overrides[child.get("lab_test_template")])
        doc.save()
    return {
        "name": result.get("name"),
        "status": result.get("status"),
        "lab_tests": templates,
    }


@frappe.whitelist()
def delete_consultation_related_record(consultation: str, doctype: str, name: str) -> dict:
    consultation_doc = _require_consultation_access(consultation)
    if doctype not in SUPPORTED_RELATED_DOCTYPES:
        frappe.throw(_("This related record type cannot be deleted here."), frappe.ValidationError)
    if consultation_doc.get("status") in {"Ready for Treatment", "Completed", "Cancelled"}:
        frappe.throw(_("Related clinical records cannot be deleted after the Consultation is Ready for Treatment."), frappe.ValidationError)
    if not name or not frappe.db.exists(doctype, name):
        frappe.throw(_("The selected related record could not be found."), frappe.DoesNotExistError)

    doc = frappe.get_doc(doctype, name)
    doc.check_permission("delete")
    link_field = "consultation" if doctype == LAB_ORDER_DOCTYPE else "linked_consultation"
    if doc.get(link_field) != consultation:
        frappe.throw(_("The selected record does not belong to this Consultation."), frappe.ValidationError)

    _assert_source_is_delete_safe(doc)
    source_type = "Lab Order" if doctype == LAB_ORDER_DOCTYPE else "Vaccination"
    _assert_plan_rows_are_removable(consultation_doc, source_type, name)
    _assert_source_has_no_finalized_billing(doctype, name, source_type)
    if doctype == VACCINATION_DOCTYPE:
        _detach_generated_vaccination_appointment(doc)

    kept_rows = [
        row
        for row in consultation_doc.get("planned_treatments") or []
        if not (row.get("source_type") == source_type and row.get("source_document") == name)
    ]
    consultation_doc.set("planned_treatments", kept_rows)
    from vetedge.services.consultation_billing_plan import _save_consultation

    _save_consultation(consultation_doc)
    _detach_nonfinal_direct_session_charges(doctype, name)
    frappe.delete_doc(doctype, name)

    billing_result = _resync_consultation_after_related_delete(consultation)
    return {
        "deleted": True,
        "doctype": doctype,
        "name": name,
        "billing": billing_result,
    }


def _assert_source_is_delete_safe(doc) -> None:
    if doc.doctype == LAB_ORDER_DOCTYPE:
        if doc.get("status") not in {"Draft", "Ordered"}:
            frappe.throw(_("Only Draft or Ordered Lab Orders can be deleted."), frappe.ValidationError)
        if any(
            row.get("result_value") not in (None, "")
            or row.get("result_text") not in (None, "")
            or row.get("result_attachment") not in (None, "")
            or row.get("result_summary") not in (None, "")
            for row in doc.get("lab_tests") or []
        ):
            frappe.throw(_("Lab Orders with entered or uploaded results cannot be deleted."), frappe.ValidationError)
    else:
        if doc.get("status") not in {"Draft", "Awaiting Payment", "Pending Administration"}:
            frappe.throw(_("Administered or cancelled Vaccination Records cannot be deleted."), frappe.ValidationError)
        if doc.get("stock_entry_reference"):
            frappe.throw(_("Stock-posted Vaccination Records cannot be deleted."), frappe.ValidationError)

    invoice_name = doc.get("linked_invoice")
    if invoice_name and frappe.db.exists("Sales Invoice", invoice_name):
        if cint(frappe.db.get_value("Sales Invoice", invoice_name, "docstatus")) == 1:
            frappe.throw(_("This record is on a submitted Sales Invoice and cannot be deleted. Use the accounting adjustment workflow instead."), frappe.ValidationError)


def _assert_plan_rows_are_removable(consultation_doc, source_type: str, source_name: str) -> None:
    for row in consultation_doc.get("planned_treatments") or []:
        if row.get("source_type") != source_type or row.get("source_document") != source_name:
            continue
        if (row.get("billing_status") or "") not in REMOVABLE_PLAN_BILLING_STATUSES:
            frappe.throw(_("This service has already reached submitted billing and cannot be deleted."), frappe.ValidationError)
        if (row.get("payment_status") or "") not in REMOVABLE_PLAN_PAYMENT_STATUSES:
            frappe.throw(_("This service has a payment allocation and cannot be deleted. Use an accounting adjustment instead."), frappe.ValidationError)


def _assert_source_has_no_finalized_billing(doctype: str, name: str, source_type: str) -> None:
    try:
        from vetedge.services.billing_core import BILLING_SESSION_CHARGE_DOCTYPE
    except Exception:
        return
    direct = frappe.get_all(
        BILLING_SESSION_CHARGE_DOCTYPE,
        filters={
            "source_doctype": doctype,
            "source_name": name,
            "billing_status": ["in", sorted(FINAL_BILLING_STATUSES)],
        },
        fields=["name"],
        limit=1,
    )
    prefix = f"consultation-plan::{source_type}::{name}::%"
    plan = frappe.get_all(
        BILLING_SESSION_CHARGE_DOCTYPE,
        filters={
            "charge_key": ["like", prefix],
            "billing_status": ["in", sorted(FINAL_BILLING_STATUSES)],
        },
        fields=["name"],
        limit=1,
    )
    if direct or plan:
        frappe.throw(_("This service has finalized billing and cannot be deleted. Use the cancellation/credit workflow instead."), frappe.ValidationError)


def _detach_nonfinal_direct_session_charges(doctype: str, name: str) -> None:
    try:
        from vetedge.services.billing_core import BILLING_SESSION_CHARGE_DOCTYPE
    except Exception:
        return
    rows = frappe.get_all(
        BILLING_SESSION_CHARGE_DOCTYPE,
        filters={"source_doctype": doctype, "source_name": name},
        fields=["parent"],
    )
    for parent in {row.get("parent") for row in rows if row.get("parent")}:
        session = frappe.get_doc("Veterinary Billing Session", parent)
        changed = False
        for charge in session.get("charges") or []:
            if charge.get("source_doctype") != doctype or charge.get("source_name") != name:
                continue
            if charge.get("billing_status") in FINAL_BILLING_STATUSES:
                frappe.throw(_("A finalized billing charge still references this service."), frappe.ValidationError)
            charge.billing_status = "Cancelled"
            changed = True
        if changed:
            session.save()


def _resync_consultation_after_related_delete(consultation: str) -> dict:
    from vetedge.services.billing_core import is_billing_sessions_enabled, resolve_billing_session, sync_source_to_billing_session

    if not is_billing_sessions_enabled():
        return {"updated": False, "reason": "billing_sessions_disabled"}
    if not resolve_billing_session(CONSULTATION_DOCTYPE, consultation):
        return {"updated": False, "reason": "no_active_billing_session"}
    result = sync_source_to_billing_session(
        CONSULTATION_DOCTYPE,
        consultation,
        confirm=True,
        confirmation_type="remove_empty_draft_invoice",
    )
    if result.get("blocked"):
        frappe.throw(result.get("message") or _("Billing prevents this deletion."), frappe.ValidationError)
    if result.get("requires_confirmation"):
        frappe.throw(result.get("message") or _("Billing requires a separate accounting action before deletion."), frappe.ValidationError)
    return result


def _detach_generated_vaccination_appointment(doc) -> None:
    appointment_name = doc.get("next_vaccination_appointment")
    if not appointment_name or not frappe.db.exists("Veterinary Appointment", appointment_name):
        return
    appointment = frappe.get_doc("Veterinary Appointment", appointment_name)
    from vetedge.services.appointment_flow import GENERATED_APPOINTMENT_MUTABLE_STATUSES

    if appointment.get("status") not in GENERATED_APPOINTMENT_MUTABLE_STATUSES:
        frappe.throw(_("The generated vaccination appointment has already progressed and this Vaccination Record cannot be deleted."), frappe.ValidationError)
    frappe.db.set_value(
        "Veterinary Appointment",
        appointment.name,
        {
            "status": "Cancelled",
            "source_doctype": None,
            "source_name": None,
            "source_field": None,
            "generated_from": None,
        },
        update_modified=False,
    )


def validate_consultation_lab_test_duplicates(doc) -> None:
    consultation = doc.get("consultation")
    if not consultation or doc.get("status") == "Cancelled":
        return
    current = {row.get("lab_test_template") for row in doc.get("lab_tests") or [] if row.get("lab_test_template")}
    previous = doc.get_doc_before_save() if getattr(doc, "get_doc_before_save", None) else None
    if previous and previous.get("consultation") == consultation:
        previous_templates = {row.get("lab_test_template") for row in previous.get("lab_tests") or [] if row.get("lab_test_template")}
        candidates = current - previous_templates
    else:
        candidates = current
    if not candidates:
        return
    parent_filters: dict[str, Any] = {"consultation": consultation, "status": ["!=", "Cancelled"]}
    if doc.get("name"):
        parent_filters["name"] = ["!=", doc.name]
    parents = frappe.get_all(LAB_ORDER_DOCTYPE, filters=parent_filters, pluck="name")
    if not parents:
        return
    duplicate = frappe.get_all(
        LAB_ORDER_ITEM_DOCTYPE,
        filters={"parent": ["in", parents], "lab_test_template": ["in", list(candidates)]},
        fields=["lab_test_template"],
        limit=1,
    )
    if duplicate:
        template = duplicate[0].get("lab_test_template")
        label = frappe.db.get_value(LAB_TEST_DOCTYPE, template, "test_name") or template
        frappe.throw(_("Lab Test {0} is already active on this Consultation.").format(label), frappe.ValidationError)


def validate_consultation_vaccination_duplicate(doc) -> None:
    consultation = doc.get("linked_consultation")
    vaccine = doc.get("vaccine")
    if not consultation or not vaccine or doc.get("status") == "Cancelled":
        return
    previous = doc.get_doc_before_save() if getattr(doc, "get_doc_before_save", None) else None
    if previous and previous.get("linked_consultation") == consultation and previous.get("vaccine") == vaccine:
        return
    filters: dict[str, Any] = {
        "linked_consultation": consultation,
        "vaccine": vaccine,
        "status": ["!=", "Cancelled"],
    }
    if doc.get("name"):
        filters["name"] = ["!=", doc.name]
    if frappe.db.exists(VACCINATION_DOCTYPE, filters):
        label = frappe.db.get_value(VACCINE_DOCTYPE, vaccine, "vaccine_name") or vaccine
        frappe.throw(_("Vaccination {0} is already active on this Consultation.").format(label), frappe.ValidationError)
