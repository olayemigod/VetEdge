from __future__ import annotations

import frappe

from vetedge.services.display_labels import get_display_label
from vetedge.services.nadis_vaccination_editor import extend_vaccination_editor_config
from vetedge.services.portal_access import require_internal_user


VACCINATION_SYSTEM_FIELDS = {
    "linked_consultation",
    "administered_by",
    "administered_on",
    "next_vaccination_appointment",
    "batch_no",
    "expiry_date",
    "billing_item",
    "amount",
    "linked_invoice",
    "stock_entry_reference",
}
PRE_ADMIN_STATUSES = {"Draft", "Awaiting Payment", "Pending Administration"}


def _field_map(state: dict) -> dict[str, dict]:
    return {str(field.get("fieldname") or ""): field for field in state.get("fields") or []}


def _align_link_labels(state: dict) -> dict:
    for field in state.get("fields") or []:
        if field.get("fieldtype") != "Link" or not field.get("value"):
            continue
        field["selected_label"] = get_display_label(field.get("options"), field.get("value"))
    return state


def _describe_vaccination_system_fields(fields: dict[str, dict], status: str, stock_posted: bool) -> None:
    batch = fields.get("batch_no")
    if batch:
        if status in PRE_ADMIN_STATUSES and not batch.get("value"):
            batch["description"] = (
                "Selected automatically from available non-expired vaccine stock when the vaccination is administered. "
                "VetEdge uses the configured FEFO expiry-control policy unless a validated manual batch is supplied by a controlled workflow/API."
            )
        else:
            batch["description"] = (
                "Batch used for this vaccination stock issue. It is locked after administration/stock allocation to preserve inventory traceability."
            )

    expiry = fields.get("expiry_date")
    if expiry:
        expiry["description"] = (
            "Derived from the selected/allocated vaccine batch and kept read-only for stock and expiry traceability."
        )

    appointment = fields.get("next_vaccination_appointment")
    if appointment:
        appointment["description"] = (
            "Created by the vaccination follow-up workflow from the Next Due Date when appointment automation is enabled."
        )

    stock_entry = fields.get("stock_entry_reference")
    if stock_entry:
        stock_entry["description"] = (
            "ERPNext Stock Entry created for the administered vaccine. Submitted stock references are never edited from the clinical modal."
        )

    if stock_posted and batch and not batch.get("value"):
        batch["description"] = (
            "Stock has already been posted. The vaccination batch is controlled by the submitted stock transaction and cannot be changed here."
        )


def _align_vaccination_state(state: dict) -> dict:
    fields = _field_map(state)
    status = str(state.get("status") or "Draft")
    billing = state.get("billing_state") or {}
    submitted = bool(billing.get("has_submitted_invoice"))
    administered = status == "Administered"
    stock_posted = bool(fields.get("stock_entry_reference", {}).get("value"))

    # Identity, workflow-produced administration metadata, inventory lineage and
    # accounting references are never edited directly from the EdgeSuite modal.
    # Their authoritative workflow actions populate them server-side.
    for fieldname in VACCINATION_SYSTEM_FIELDS:
        field = fields.get(fieldname)
        if field:
            field["read_only"] = 1

    for fieldname in ("administered_by", "administered_on"):
        field = fields.get(fieldname)
        if field and status in PRE_ADMIN_STATUSES:
            field["value"] = ""
            field["selected_label"] = ""

    _describe_vaccination_system_fields(fields, status, stock_posted)

    # Vaccine and rate are service-definition inputs while billing is Draft.
    # Once a submitted invoice, administration, or stock posting exists they
    # become immutable from this clinical editor.
    vaccine = fields.get("vaccine")
    if vaccine:
        vaccine["read_only"] = int(submitted or administered or stock_posted)

    rate = fields.get("rate")
    if rate:
        rate["read_only"] = int(submitted or administered or stock_posted)
        rate["description"] = (
            "Editable only before invoice submission, vaccine administration or stock posting. "
            "Permitted changes synchronize to draft billing."
        )

    next_due = fields.get("next_due_date")
    if next_due:
        next_due["read_only"] = int(stock_posted and administered)

    reason = fields.get("vaccination_reason")
    if reason:
        reason["description"] = (
            "Regulatory classification used by the official NADIS vaccination report. "
            "It does not change billing, stock posting or administration evidence."
        )

    state["can_save"] = bool(
        state.get("can_save") and any(not field.get("read_only") for field in fields.values())
    )
    state["batch_selection_policy"] = "FEFO"
    return state


@frappe.whitelist()
def get_clinical_record_editor(doctype: str, name: str) -> dict:
    require_internal_user()
    from vetedge.services import clinical_record_editor

    extend_vaccination_editor_config(clinical_record_editor.RECORD_CONFIG)
    state = _align_link_labels(clinical_record_editor.get_clinical_record_editor(doctype=doctype, name=name))
    if doctype == "Veterinary Vaccination Record":
        state = _align_vaccination_state(state)
    return state


@frappe.whitelist()
def get_lab_result_editor(lab_order: str, row_name: str) -> dict:
    require_internal_user()
    from vetedge.services.clinical_record_state import get_lab_result_editor as original

    return original(lab_order=lab_order, row_name=row_name)
