from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cstr


BRANCH_REQUIRED_DOCTYPES = {
    "Veterinary Consultation": "service_branch",
    "Veterinary Lab Order": "service_branch",
    "Veterinary Vaccination Record": "service_branch",
    "Veterinary Appointment": "branch",
    "Pet Grooming Appointment": "service_branch",
    "Pet Grooming Session": "service_branch",
    "Pet Boarding Booking": "service_branch",
    "Pet Boarding Stay": "service_branch",
    "Pet Boarding Care Record": "service_branch",
    "Kennel": "branch",
}

VETEDGE_INVOICE_REMARK_TOKENS = (
    "consultation billing for",
    "lab billing for",
    "vaccination billing for",
    "boarding billing for",
    "grooming billing for",
    "registration billing",
)

VETEDGE_STOCK_ENTRY_REMARK_TOKENS = (
    "vaccination stock issue",
)

VETEDGE_STOCK_LINK_FIELDS = (
    "consultation",
    "linked_consultation",
    "patient",
    "linked_patient",
)


def enforce_branch_integrity(doc, method: str | None = None) -> None:
    fieldname = BRANCH_REQUIRED_DOCTYPES.get(getattr(doc, "doctype", None))
    if not fieldname:
        return
    _require_non_empty_branch(doc, fieldname)


def enforce_vetedge_invoice_branch(doc, method: str | None = None) -> None:
    if getattr(doc, "doctype", None) != "Sales Invoice":
        return
    if not _is_vetedge_invoice(doc):
        return
    _require_non_empty_branch(doc, "branch")


def enforce_vetedge_stock_entry_branch(doc, method: str | None = None) -> None:
    if getattr(doc, "doctype", None) != "Stock Entry":
        return
    if not _is_vetedge_stock_entry(doc):
        return
    _require_non_empty_branch(doc, "branch")


def _require_non_empty_branch(doc, fieldname: str) -> None:
    meta = getattr(doc, "meta", None) or frappe.get_meta(doc.doctype)
    if not meta.has_field(fieldname):
        return
    value = cstr(doc.get(fieldname) or "").strip()
    if value:
        return
    label = meta.get_label(fieldname) or frappe.unscrub(fieldname)
    frappe.throw(
        _("{0} is required before this {1} can be saved.").format(label, doc.doctype),
        frappe.ValidationError,
    )


def _is_vetedge_invoice(doc) -> bool:
    remarks = cstr(getattr(doc, "remarks", "") or "").lower()
    if any(token in remarks for token in VETEDGE_INVOICE_REMARK_TOKENS):
        return True
    return False


def _is_vetedge_stock_entry(doc) -> bool:
    remarks = cstr(getattr(doc, "remarks", "") or "").lower()
    if any(token in remarks for token in VETEDGE_STOCK_ENTRY_REMARK_TOKENS):
        return True
    meta = getattr(doc, "meta", None) or frappe.get_meta(doc.doctype)
    for fieldname in VETEDGE_STOCK_LINK_FIELDS:
        if meta.has_field(fieldname) and doc.get(fieldname):
            return True
    return False
