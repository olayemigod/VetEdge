from __future__ import annotations

from collections import OrderedDict

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from vetedge.services.portal_access import require_internal_user


LAB_ORDER_DOCTYPE = "Veterinary Lab Order"
BILLING_SESSION_DOCTYPE = "Veterinary Billing Session"
BILLING_SESSION_CHARGE_DOCTYPE = "Veterinary Billing Session Charge"
NOTIFICATION_ITEM_DOCTYPE = "Veterinary Notification Item"

RESULT_EVIDENCE_FIELDS = (
    "result_value",
    "result_text",
    "result_attachment",
    "remarks",
)
RESULT_EVIDENCE_ORDER_STATUSES = {
    "Result Entered",
    "Awaiting Review",
    "Reviewed",
    "Completed",
}
RESULT_EVIDENCE_ROW_STATUSES = {
    "Result Entered",
    "Awaiting Review",
    "Reviewed",
    "Completed",
}
RESULT_EVIDENCE_RESULT_STATUSES = {
    "Entered",
    "Awaiting Review",
    "Reviewed",
}

HARD_BLOCK_PAYMENT_STATES = {"Partly Paid", "Paid"}
HARD_BLOCK_PLAN_PAYMENT_STATUSES = {"Partly Paid", "Paid"}
HARD_BLOCK_PLAN_BILLING_STATUSES = {"Paid"}
RETIRED_CHARGE_STATUSES = {"Cancelled", "Skipped"}
ALLOWED_BILLING_CONFIRMATIONS = {"remove_empty_draft_invoice", "cancel_unpaid_invoice"}


def _previous_doc(doc):
    getter = getattr(doc, "get_doc_before_save", None)
    return getter() if callable(getter) else None


def _source_doc_for_evidence(doc):
    return _previous_doc(doc) or doc


def _has_result_evidence(doc) -> bool:
    source = _source_doc_for_evidence(doc)
    if source.get("status") in RESULT_EVIDENCE_ORDER_STATUSES:
        return True

    for row in source.get("lab_tests") or []:
        if row.get("status") in RESULT_EVIDENCE_ROW_STATUSES:
            return True
        if row.get("result_status") in RESULT_EVIDENCE_RESULT_STATUSES:
            return True
        if any(row.get(fieldname) not in (None, "") for fieldname in RESULT_EVIDENCE_FIELDS):
            return True
    return False


def _get_consultation_plan_rows(doc) -> list:
    source = _source_doc_for_evidence(doc)
    consultation_name = source.get("consultation")
    if not consultation_name or not frappe.db.exists("Veterinary Consultation", consultation_name):
        return []

    consultation = frappe.get_doc("Veterinary Consultation", consultation_name)
    return [
        row
        for row in consultation.get("planned_treatments") or []
        if row.get("source_type") == "Lab Order" and row.get("source_document") == source.name
    ]


def _invoice_state(invoice_name: str) -> dict:
    if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
        return {
            "invoice": invoice_name,
            "docstatus": None,
            "status": None,
            "grand_total": 0.0,
            "paid_amount": 0.0,
            "outstanding_amount": 0.0,
            "payment_state": "Missing",
            "remarks": "",
        }

    invoice = frappe.db.get_value(
        "Sales Invoice",
        invoice_name,
        ["docstatus", "status", "grand_total", "paid_amount", "outstanding_amount", "remarks"],
        as_dict=True,
    ) or {}
    docstatus = cint(invoice.get("docstatus"))
    grand_total = flt(invoice.get("grand_total"))
    paid_amount = flt(invoice.get("paid_amount"))
    outstanding_amount = flt(invoice.get("outstanding_amount"))

    if docstatus == 1:
        try:
            from vetedge.services.payment_gate import get_invoice_payment_state

            payment = get_invoice_payment_state(invoice_name) or {}
            paid_amount = flt(payment.get("paid_amount", paid_amount))
            outstanding_amount = flt(payment.get("outstanding_amount", outstanding_amount))
        except Exception:
            pass

    if docstatus == 0:
        payment_state = "Draft"
    elif docstatus == 2:
        payment_state = "Cancelled"
    elif docstatus == 1 and outstanding_amount <= 0:
        payment_state = "Paid"
    elif docstatus == 1 and (paid_amount > 0 or (grand_total and outstanding_amount < grand_total)):
        payment_state = "Partly Paid"
    elif docstatus == 1:
        payment_state = "Unpaid"
    else:
        payment_state = "Missing"

    return {
        "invoice": invoice_name,
        "docstatus": docstatus,
        "status": invoice.get("status"),
        "grand_total": grand_total,
        "paid_amount": paid_amount,
        "outstanding_amount": outstanding_amount,
        "payment_state": payment_state,
        "remarks": invoice.get("remarks") or "",
    }


def _collect_invoice_evidence(doc) -> list[dict]:
    source = _source_doc_for_evidence(doc)
    invoice_names: OrderedDict[str, None] = OrderedDict()

    linked_invoice = source.get("linked_invoice")
    if linked_invoice:
        invoice_names[linked_invoice] = None

    try:
        from vetedge.services.lab_billing_context import get_lab_billing_evidence

        evidence = get_lab_billing_evidence(source) or {}
        for invoice_name in evidence.get("invoice_names") or []:
            if invoice_name:
                invoice_names[invoice_name] = None
        for row_evidence in (evidence.get("row_billing") or {}).values():
            invoice_name = row_evidence.get("invoice") if row_evidence else None
            if invoice_name:
                invoice_names[invoice_name] = None
    except Exception:
        pass

    return [_invoice_state(name) for name in invoice_names]


def _find_charge_rows(doc) -> list[dict]:
    if not frappe.db.exists("DocType", BILLING_SESSION_CHARGE_DOCTYPE):
        return []

    source = _source_doc_for_evidence(doc)
    fields = [
        "name",
        "parent",
        "source_doctype",
        "source_name",
        "source_detail_name",
        "charge_key",
        "invoice",
        "invoice_item_name",
        "billing_status",
        "notes",
    ]
    rows = frappe.get_all(
        BILLING_SESSION_CHARGE_DOCTYPE,
        filters={"source_doctype": LAB_ORDER_DOCTYPE, "source_name": source.name},
        fields=fields,
        limit=200,
    )

    consultation_name = source.get("consultation")
    if consultation_name:
        rows.extend(
            frappe.get_all(
                BILLING_SESSION_CHARGE_DOCTYPE,
                filters={
                    "source_doctype": "Veterinary Consultation",
                    "source_name": consultation_name,
                    "charge_key": ["like", f"consultation-plan::Lab Order::{source.name}::%"],
                },
                fields=fields,
                limit=200,
            )
        )

    deduped: OrderedDict[str, dict] = OrderedDict()
    for row in rows:
        if row.get("name"):
            deduped[row.name] = row
    return list(deduped.values())


def _billing_core_invoice_has_unrelated_active_charges(invoice_name: str, target_rows: list[dict]) -> bool:
    """Fail closed when a submitted invoice contains anything beyond this Lab Order.

    Shared-invoice safety must be invoice-wide, not limited to the Billing Session
    that happens to own the Lab charge. This also protects invoices whose other
    service charge was created in a different session or whose Billing Session
    linkage is incomplete/stale.
    """
    target_names = {
        row.get("name")
        for row in target_rows
        if row.get("name") and row.get("invoice") == invoice_name
    }
    target_charge_keys = {
        str(row.get("charge_key"))
        for row in target_rows
        if row.get("invoice") == invoice_name and row.get("charge_key")
    }
    if not target_names or not target_charge_keys:
        return True

    invoice_charge_rows = frappe.get_all(
        BILLING_SESSION_CHARGE_DOCTYPE,
        filters={"invoice": invoice_name},
        fields=["name", "charge_key", "billing_status"],
        limit=1000,
    )
    if any(
        row.get("name") not in target_names
        and row.get("billing_status") not in RETIRED_CHARGE_STATUSES
        for row in invoice_charge_rows
    ):
        return True

    # A submitted invoice may also contain manual or otherwise untracked lines.
    # Never auto-cancel it unless every invoice item can be proven to belong to
    # this Lab Order's Billing Core charge keys.
    try:
        from vetedge.services.billing_core import extract_charge_key_from_invoice_item

        invoice = frappe.get_doc("Sales Invoice", invoice_name)
        for item in invoice.get("items") or []:
            charge_key = extract_charge_key_from_invoice_item(item)
            if not charge_key or str(charge_key) not in target_charge_keys:
                return True
    except Exception:
        return True

    return False


def _legacy_invoice_is_dedicated_to_lab_order(doc, invoice_state: dict) -> bool:
    source = _source_doc_for_evidence(doc)
    if source.get("consultation"):
        return False
    if source.get("linked_invoice") != invoice_state.get("invoice"):
        return False
    remarks = str(invoice_state.get("remarks") or "").lower()
    return source.name.lower() in remarks and "lab billing" in remarks


def _build_financial_blockers(doc, invoice_evidence: list[dict], plan_rows: list, charge_rows: list[dict]) -> list[str]:
    blockers: list[str] = []
    source = _source_doc_for_evidence(doc)

    paid_or_partial = [row for row in invoice_evidence if row.get("payment_state") in HARD_BLOCK_PAYMENT_STATES]
    if paid_or_partial:
        names = ", ".join(row.get("invoice") for row in paid_or_partial if row.get("invoice"))
        blockers.append(
            _(
                "This Lab Order has paid or partly-paid invoice evidence ({0}). "
                "Use an approved refund, credit-note, or accounting-correction workflow before cancelling it."
            ).format(names)
        )

    if any(row.get("billing_status") == "Paid" for row in charge_rows):
        blockers.append(_("This Lab Order has paid Billing Session charges and cannot be ordinarily cancelled."))

    protected_plan_rows = [
        row
        for row in plan_rows
        if row.get("billing_status") in HARD_BLOCK_PLAN_BILLING_STATUSES
        or row.get("payment_status") in HARD_BLOCK_PLAN_PAYMENT_STATUSES
    ]
    if protected_plan_rows:
        blockers.append(
            _(
                "Consultation billing for this Lab Order is partly paid or paid. "
                "Use an approved financial correction workflow before cancellation."
            )
        )

    for invoice in invoice_evidence:
        if invoice.get("payment_state") not in {"Draft", "Unpaid"}:
            continue
        invoice_name = invoice.get("invoice")
        target_rows = [row for row in charge_rows if row.get("invoice") == invoice_name]
        if target_rows:
            if invoice.get("payment_state") == "Unpaid" and _billing_core_invoice_has_unrelated_active_charges(
                invoice_name, target_rows
            ):
                blockers.append(
                    _(
                        "Submitted invoice {0} also contains active or unproven charges for other services. "
                        "VetEdge will not alter a submitted shared invoice; resolve those services separately before cancelling this Lab Order."
                    ).format(invoice_name)
                )
            continue

        if not _legacy_invoice_is_dedicated_to_lab_order(source, invoice):
            blockers.append(
                _(
                    "VetEdge cannot safely prove that invoice {0} belongs only to this Lab Order. "
                    "Automatic cancellation is blocked to protect unrelated accounting entries."
                ).format(invoice_name)
            )

    if not invoice_evidence and any(
        row.get("billing_status") in {"Draft Invoiced", "Submitted Invoiced"}
        or row.get("payment_status") == "Unpaid"
        for row in plan_rows
    ):
        blockers.append(
            _(
                "Consultation billing shows an invoiced Lab charge but its Sales Invoice evidence could not be resolved. "
                "Reconcile the billing link before cancellation."
            )
        )

    return blockers


def build_lab_order_cancellation_preflight(doc) -> dict:
    invoice_evidence = _collect_invoice_evidence(doc)
    plan_rows = _get_consultation_plan_rows(doc)
    charge_rows = _find_charge_rows(doc)
    blockers = _build_financial_blockers(doc, invoice_evidence, plan_rows, charge_rows)
    has_result_evidence = _has_result_evidence(doc)

    if has_result_evidence:
        blockers.insert(
            0,
            _(
                "This Lab Order already contains entered, reviewed, or completed diagnostic result evidence. "
                "Use a controlled clinical correction/void process instead of ordinary cancellation."
            ),
        )

    return {
        "can_cancel": not blockers,
        "message": " ".join(blockers),
        "blockers": blockers,
        "has_result_evidence": has_result_evidence,
        "invoice_evidence": invoice_evidence,
        "billing_charge_count": len(charge_rows),
        "consultation_plan_rows": [
            {
                "name": row.get("name"),
                "billing_status": row.get("billing_status"),
                "payment_status": row.get("payment_status"),
                "source_detail_name": row.get("source_detail_name"),
            }
            for row in plan_rows
        ],
    }


@frappe.whitelist()
def get_lab_order_cancellation_preflight(lab_order: str) -> dict:
    require_internal_user()
    from vetedge.services.permissions import can_access_lab_order

    can_access_lab_order(frappe.session.user, lab_order, raise_exception=True)
    if not frappe.db.exists(LAB_ORDER_DOCTYPE, lab_order):
        frappe.throw(_("The selected Lab Order could not be found."), frappe.DoesNotExistError)
    return build_lab_order_cancellation_preflight(frappe.get_doc(LAB_ORDER_DOCTYPE, lab_order))


def _retire_target_charge_rows(doc) -> tuple[int, set[str]]:
    rows = _find_charge_rows(doc)
    retired = 0
    sessions: set[str] = set()

    for row in rows:
        if row.get("billing_status") == "Paid":
            frappe.throw(_("Paid Lab billing charges cannot be retired by ordinary cancellation."), frappe.ValidationError)
        if row.get("parent"):
            sessions.add(row.get("parent"))
        if row.get("billing_status") in RETIRED_CHARGE_STATUSES:
            continue

        note = _("Retired because Lab Order {0} was cancelled.").format(_source_doc_for_evidence(doc).name)
        notes = "; ".join(part for part in [row.get("notes"), note] if part)
        frappe.db.set_value(
            BILLING_SESSION_CHARGE_DOCTYPE,
            row.name,
            {"billing_status": "Cancelled", "notes": notes},
            update_modified=False,
        )
        retired += 1

    return retired, sessions


def _reconcile_billing_sessions(session_names: set[str]) -> list[dict]:
    if not session_names:
        return []

    from vetedge.services.billing_core import sync_session_charges_to_invoice

    results = []
    for session_name in sorted(name for name in session_names if name):
        if not frappe.db.exists(BILLING_SESSION_DOCTYPE, session_name):
            continue
        result = sync_session_charges_to_invoice(session_name) or {}
        if result.get("blocked"):
            frappe.throw(
                result.get("message") or _("Billing reconciliation blocked Lab cancellation."),
                frappe.ValidationError,
            )
        if result.get("requires_confirmation"):
            confirmation_type = result.get("confirmation_type")
            if confirmation_type not in ALLOWED_BILLING_CONFIRMATIONS:
                frappe.throw(
                    result.get("message") or _("Billing requires a separate accounting decision before Lab cancellation."),
                    frappe.ValidationError,
                )
            result = sync_session_charges_to_invoice(
                session_name,
                confirm=True,
                confirmation_type=confirmation_type,
            ) or {}
            if result.get("blocked") or result.get("requires_confirmation"):
                frappe.throw(
                    result.get("message") or _("Billing reconciliation did not complete safely."),
                    frappe.ValidationError,
                )
        results.append(result)
    return results


def _cleanup_legacy_direct_invoices(doc, invoice_evidence: list[dict], charge_rows: list[dict]) -> list[str]:
    source = _source_doc_for_evidence(doc)
    handled = []
    charge_invoices = {row.get("invoice") for row in charge_rows if row.get("invoice")}

    for invoice_state in invoice_evidence:
        invoice_name = invoice_state.get("invoice")
        if not invoice_name or invoice_name in charge_invoices:
            continue
        payment_state = invoice_state.get("payment_state")
        if payment_state in {"Cancelled", "Missing"}:
            continue
        if payment_state in HARD_BLOCK_PAYMENT_STATES:
            frappe.throw(_("Paid or partly-paid Lab invoices require a financial correction workflow."), frappe.ValidationError)
        if payment_state not in {"Draft", "Unpaid"}:
            continue
        if not _legacy_invoice_is_dedicated_to_lab_order(source, invoice_state):
            frappe.throw(
                _("VetEdge cannot safely prove invoice {0} is dedicated to this Lab Order.").format(invoice_name),
                frappe.ValidationError,
            )

        from vetedge.services.billing_core import (
            detach_invoice_from_vetedge_sources,
            run_with_billing_core_sync_flag,
        )

        invoice = frappe.get_doc("Sales Invoice", invoice_name)
        detach_invoice_from_vetedge_sources(invoice_name, reason="lab_order_cancelled")
        if source.get("linked_invoice") == invoice_name:
            source.linked_invoice = None
            if doc is not source:
                doc.linked_invoice = None
        if payment_state == "Draft":
            run_with_billing_core_sync_flag(lambda: frappe.delete_doc("Sales Invoice", invoice_name))
        else:
            run_with_billing_core_sync_flag(invoice.cancel)
        handled.append(invoice_name)

    return handled


def _remove_safe_consultation_plan_rows(doc) -> int:
    source = _source_doc_for_evidence(doc)
    consultation_name = source.get("consultation")
    if not consultation_name or not frappe.db.exists("Veterinary Consultation", consultation_name):
        return 0

    consultation = frappe.get_doc("Veterinary Consultation", consultation_name)
    matching = [
        row
        for row in consultation.get("planned_treatments") or []
        if row.get("source_type") == "Lab Order" and row.get("source_document") == source.name
    ]
    if not matching:
        return 0

    protected = [
        row
        for row in matching
        if row.get("billing_status") in HARD_BLOCK_PLAN_BILLING_STATUSES
        or row.get("payment_status") in HARD_BLOCK_PLAN_PAYMENT_STATUSES
    ]
    if protected:
        frappe.throw(
            _("Lab cancellation cannot remove partly-paid or paid Consultation treatment rows."),
            frappe.ValidationError,
        )

    remaining = [
        row
        for row in consultation.get("planned_treatments") or []
        if not (row.get("source_type") == "Lab Order" and row.get("source_document") == source.name)
    ]
    consultation.set("planned_treatments", remaining)

    from vetedge.services.consultation_billing_plan import _save_consultation

    _save_consultation(consultation)
    return len(matching)


def _archive_lab_notifications(doc, *, detach: bool = False) -> int:
    if not frappe.db.exists("DocType", NOTIFICATION_ITEM_DOCTYPE):
        return 0

    source = _source_doc_for_evidence(doc)
    rows = frappe.get_all(
        NOTIFICATION_ITEM_DOCTYPE,
        filters={"reference_doctype": LAB_ORDER_DOCTYPE, "reference_name": source.name},
        fields=["name", "frappe_notification_log"],
        limit=500,
    )
    archived_on = now_datetime()
    for row in rows:
        values = {
            "status": "Archived",
            "archived_on": archived_on,
            "action_url": None,
        }
        if detach:
            values.update({"reference_doctype": None, "reference_name": None})
        frappe.db.set_value(NOTIFICATION_ITEM_DOCTYPE, row.name, values, update_modified=False)

        notification_log = row.get("frappe_notification_log")
        if notification_log and frappe.db.exists("Notification Log", notification_log):
            log_values = {"read": 1, "link": None}
            if detach:
                log_values.update({"document_type": None, "document_name": None})
            frappe.db.set_value("Notification Log", notification_log, log_values, update_modified=False)
    return len(rows)


def _detach_deleted_lab_billing_links(doc) -> None:
    source = _source_doc_for_evidence(doc)
    if frappe.db.exists("DocType", BILLING_SESSION_CHARGE_DOCTYPE):
        rows = frappe.get_all(
            BILLING_SESSION_CHARGE_DOCTYPE,
            filters={"source_doctype": LAB_ORDER_DOCTYPE, "source_name": source.name},
            fields=["name", "notes"],
            limit=500,
        )
        for row in rows:
            note = _("Source Lab Order {0} was deleted after safe cancellation cleanup.").format(source.name)
            notes = "; ".join(part for part in [row.get("notes"), note] if part)
            frappe.db.set_value(
                BILLING_SESSION_CHARGE_DOCTYPE,
                row.name,
                {
                    "source_doctype": None,
                    "source_name": None,
                    "source_detail_name": None,
                    "notes": notes,
                },
                update_modified=False,
            )

    if frappe.db.exists("DocType", BILLING_SESSION_DOCTYPE):
        for doctype_field, name_field in (
            ("source_context_doctype", "source_context_name"),
            ("created_from_doctype", "created_from_name"),
        ):
            rows = frappe.get_all(
                BILLING_SESSION_DOCTYPE,
                filters={doctype_field: LAB_ORDER_DOCTYPE, name_field: source.name},
                fields=["name"],
                limit=100,
            )
            for row in rows:
                frappe.db.set_value(
                    BILLING_SESSION_DOCTYPE,
                    row.name,
                    {doctype_field: None, name_field: None},
                    update_modified=False,
                )


def _cleanup_safe_cancellation(doc, *, delete: bool = False) -> dict:
    invoice_evidence = _collect_invoice_evidence(doc)
    charge_rows = _find_charge_rows(doc)
    retired_count, sessions = _retire_target_charge_rows(doc)
    billing_results = _reconcile_billing_sessions(sessions)
    legacy_invoices = _cleanup_legacy_direct_invoices(doc, invoice_evidence, charge_rows)
    removed_plan_rows = _remove_safe_consultation_plan_rows(doc)
    notification_count = _archive_lab_notifications(doc, detach=delete)
    if delete:
        _detach_deleted_lab_billing_links(doc)

    return {
        "retired_billing_charges": retired_count,
        "billing_results": billing_results,
        "legacy_invoices": legacy_invoices,
        "removed_consultation_plan_rows": removed_plan_rows,
        "archived_notifications": notification_count,
    }


def enforce_lab_order_cancellation(doc) -> None:
    if doc.get("status") != "Cancelled":
        return

    previous = _previous_doc(doc)
    if not previous:
        frappe.throw(_("A new Lab Order cannot be created directly as Cancelled."), frappe.ValidationError)
    if previous.get("status") == "Cancelled":
        return

    preflight = build_lab_order_cancellation_preflight(doc)
    if not preflight.get("can_cancel"):
        frappe.throw(
            preflight.get("message") or _("This Lab Order cannot be cancelled safely."),
            frappe.ValidationError,
        )

    _cleanup_safe_cancellation(doc)


def enforce_lab_order_delete(doc) -> None:
    if cint(doc.get("docstatus")) != 0:
        frappe.throw(_("Submitted Frappe documents cannot be deleted by the Lab cleanup workflow."), frappe.ValidationError)
    if doc.get("status") not in {"Draft", "Ordered", "Cancelled"}:
        frappe.throw(
            _("Only Draft, Ordered, or safely Cancelled Lab Orders without clinical result history can be deleted."),
            frappe.ValidationError,
        )

    preflight = build_lab_order_cancellation_preflight(doc)
    if not preflight.get("can_cancel"):
        frappe.throw(
            preflight.get("message") or _("This Lab Order cannot be deleted safely."),
            frappe.ValidationError,
        )

    _cleanup_safe_cancellation(doc, delete=True)
