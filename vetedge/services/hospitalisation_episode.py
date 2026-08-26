from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, now_datetime

from vetedge.services.hospitalisation_permissions import validate_hospitalisation_branch_access
from vetedge.services.permissions import get_current_user, get_veterinary_doctor_users
from vetedge.services.portal_access import require_internal_user


HOSPITALISATION_DOCTYPE = "Veterinary Hospitalisation"
CARE_LOCATION_DOCTYPE = "Veterinary Care Location"
ACTIVE_STATUSES = {"Admitted", "Under Care", "Ready for Discharge"}
CLOSED_STATUSES = {"Discharged", "Cancelled"}
ACTIVITY_TYPES = {
    "Vitals",
    "Medication",
    "Vaccination",
    "Fluid Therapy",
    "Feeding",
    "Nursing Note",
    "Wound Care",
    "Lab",
    "Imaging",
    "Procedure",
    "Oxygen / Nebulisation",
    "Owner Communication",
    "Other",
}
EDITABLE_CONTEXT_FIELDS = {
    "attending_veterinarian",
    "admission_reason",
    "care_level",
    "isolation_required",
}


def _clean(value: Any) -> str:
    return cstr(value or "").strip()


def _bounded_limit(value: int | str | None, default: int = 20, maximum: int = 50) -> int:
    try:
        resolved = int(value or default)
    except (TypeError, ValueError):
        resolved = default
    return min(max(resolved, 1), maximum)


def _load_hospitalisation(name: str, *, write: bool = False):
    require_internal_user()
    if not _clean(name):
        frappe.throw(_("Hospitalisation is required."), frappe.ValidationError)
    if not frappe.db.exists(HOSPITALISATION_DOCTYPE, name):
        frappe.throw(_("Veterinary Hospitalisation {0} could not be found.").format(name), frappe.DoesNotExistError)

    doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, name)
    doc.check_permission("write" if write else "read")
    validate_hospitalisation_branch_access(doc)
    return doc


def _can_write(doc) -> bool:
    try:
        return bool(frappe.has_permission(HOSPITALISATION_DOCTYPE, ptype="write", doc=doc))
    except Exception:
        return False


def _document_label(doctype: str, name: str | None, fallback_field: str | None = None) -> str:
    if not name:
        return ""
    try:
        meta = frappe.get_meta(doctype)
        fieldname = fallback_field or meta.title_field or "name"
        return frappe.db.get_value(doctype, name, fieldname) or name
    except Exception:
        return name


def _user_label(user: str | None) -> str:
    return _document_label("User", user, "full_name") if user else ""


def _invoice_summary(invoice_name: str | None) -> dict[str, Any]:
    if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
        return {}
    try:
        invoice = frappe.get_doc("Sales Invoice", invoice_name)
        invoice.check_permission("read")
    except Exception:
        return {"name": invoice_name}
    return {
        "name": invoice.name,
        "status": invoice.get("status"),
        "docstatus": invoice.docstatus,
        "grand_total": flt(invoice.get("grand_total")),
        "outstanding_amount": flt(invoice.get("outstanding_amount")),
        "currency": invoice.get("currency"),
    }


def _activity_payload(row) -> dict[str, Any]:
    return {
        "name": row.get("name"),
        "activity_datetime": row.get("activity_datetime"),
        "activity_type": row.get("activity_type"),
        "performed_by": row.get("performed_by"),
        "performed_by_label": _user_label(row.get("performed_by")),
        "clinical_notes": row.get("clinical_notes"),
        "billable": cint(row.get("billable")),
        "billing_status": row.get("billing_status"),
        "item": row.get("item"),
        "item_label": _document_label("Item", row.get("item"), "item_name") if row.get("item") else "",
        "qty": flt(row.get("qty")),
        "uom": row.get("uom"),
        "stock_affecting": cint(row.get("stock_affecting")),
        "stock_status": row.get("stock_status"),
        "source_warehouse": row.get("source_warehouse"),
        "stock_entry": row.get("stock_entry"),
        "posted_stock_qty": flt(row.get("posted_stock_qty")),
        "stock_posting_message": row.get("stock_posting_message"),
        "stock_posted_on": row.get("stock_posted_on"),
        "linked_doctype": row.get("linked_doctype"),
        "linked_document": row.get("linked_document"),
    }


def _charge_payload(row) -> dict[str, Any]:
    return {
        "name": row.get("name"),
        "activity_type": row.get("activity_type"),
        "charge_category": row.get("charge_category"),
        "charge_date": row.get("charge_date"),
        "item": row.get("item"),
        "item_name": row.get("item_name") or _document_label("Item", row.get("item"), "item_name"),
        "description": row.get("description"),
        "qty": flt(row.get("qty")),
        "uom": row.get("uom"),
        "rate": flt(row.get("rate")),
        "amount": flt(row.get("amount")),
        "pricing_source": row.get("pricing_source"),
        "billing_status": row.get("billing_status"),
        "sales_invoice": row.get("sales_invoice"),
        "care_level": row.get("care_level"),
        "notes": row.get("notes"),
    }


def _capabilities(doc) -> dict[str, bool]:
    can_write = _can_write(doc)
    status = _clean(doc.get("status")) or "Draft"
    active = status in ACTIVE_STATUSES
    open_episode = status not in CLOSED_STATUSES
    return {
        "can_write": can_write,
        "can_admit": can_write and status == "Draft",
        "can_add_clinical_activity": can_write and open_episode,
        "can_assign_care_location": can_write and active,
        "can_release_care_location": can_write and active and bool(doc.get("care_location")),
        "can_post_stock": can_write and active,
        "can_manage_charges": can_write and status != "Cancelled",
        "can_bill": can_write and status != "Cancelled",
        "can_check_discharge": can_write and active,
        "can_discharge": can_write and active,
        "can_open_native_form": True,
    }


def _episode_payload(doc) -> dict[str, Any]:
    patient = doc.get("patient")
    owner = doc.get("customer")
    veterinarian = doc.get("attending_veterinarian")
    care_location = doc.get("care_location")
    activities = [_activity_payload(row) for row in (doc.get("activities") or [])]
    charges = [_charge_payload(row) for row in (doc.get("charge_items") or [])]
    pending_stock = sum(1 for row in activities if row.get("stock_affecting") and row.get("stock_status") == "Pending")
    pending_billable = sum(1 for row in activities if row.get("billable") and row.get("billing_status") == "Pending Charge")
    pending_charges = sum(1 for row in charges if row.get("billing_status") == "Pending Invoice")

    return {
        "name": doc.name,
        "modified": cstr(doc.modified),
        "title": doc.get("hospitalisation_title") or doc.get("patient_name") or doc.name,
        "status": doc.get("status") or "Draft",
        "patient": patient,
        "patient_label": doc.get("patient_name") or _document_label("Veterinary Patient", patient, "patient_name"),
        "owner": owner,
        "owner_label": _document_label("Customer", owner, "customer_name"),
        "service_branch": doc.get("service_branch"),
        "company": doc.get("company"),
        "linked_consultation": doc.get("linked_consultation"),
        "attending_veterinarian": veterinarian,
        "attending_veterinarian_label": _user_label(veterinarian),
        "admitted_by": doc.get("admitted_by"),
        "admitted_by_label": _user_label(doc.get("admitted_by")),
        "admission_datetime": doc.get("admission_datetime"),
        "admission_reason": doc.get("admission_reason"),
        "care_level": doc.get("care_level") or "Standard",
        "care_location_type": doc.get("care_location_type") or "Not Assigned",
        "care_location": care_location,
        "care_location_label": _document_label(CARE_LOCATION_DOCTYPE, care_location, "location_name"),
        "care_location_status": doc.get("care_location_status"),
        "care_location_assigned_on": doc.get("care_location_assigned_on"),
        "care_location_released_on": doc.get("care_location_released_on"),
        "isolation_required": cint(doc.get("isolation_required")),
        "sales_invoice": doc.get("sales_invoice"),
        "invoice_status": doc.get("invoice_status") or "Not Invoiced",
        "payment_gate_status": doc.get("payment_gate_status") or "Not Checked",
        "payment_gate_message": doc.get("payment_gate_message"),
        "invoice": _invoice_summary(doc.get("sales_invoice")),
        "discharged_by": doc.get("discharged_by"),
        "discharged_by_label": _user_label(doc.get("discharged_by")),
        "discharge_datetime": doc.get("discharge_datetime"),
        "discharge_summary": doc.get("discharge_summary"),
        "condition_at_discharge": doc.get("condition_at_discharge"),
        "discharge_instructions": doc.get("discharge_instructions"),
        "follow_up_date": doc.get("follow_up_date"),
        "follow_up_notes": doc.get("follow_up_notes"),
        "discharge_billing_status": doc.get("discharge_billing_status") or "Not Checked",
        "discharge_message": doc.get("discharge_message"),
        "activities": activities,
        "charge_items": charges,
        "signals": {
            "pending_stock": pending_stock,
            "pending_billable_activities": pending_billable,
            "pending_charges": pending_charges,
        },
        "capabilities": _capabilities(doc),
    }


def _parse_payload(payload) -> dict[str, Any]:
    if isinstance(payload, str):
        payload = frappe.parse_json(payload)
    return payload if isinstance(payload, dict) else {}


def _assert_not_stale(doc, modified: str | None) -> None:
    if modified and cstr(doc.modified) != cstr(modified):
        frappe.throw(
            _("This Hospitalisation changed after the page was loaded. Refresh and try again."),
            frappe.TimestampMismatchError,
        )


@frappe.whitelist()
def get_hospitalisation_episode(name: str) -> dict[str, Any]:
    doc = _load_hospitalisation(name)
    return _episode_payload(doc)


@frappe.whitelist()
def save_hospitalisation_episode_context(name: str, values=None, modified: str | None = None) -> dict[str, Any]:
    doc = _load_hospitalisation(name, write=True)
    _assert_not_stale(doc, modified)
    if _clean(doc.get("status")) in CLOSED_STATUSES:
        frappe.throw(_("Closed Hospitalisation episodes are read-only."), frappe.ValidationError)

    values = _parse_payload(values)
    for fieldname in EDITABLE_CONTEXT_FIELDS:
        if fieldname not in values:
            continue
        value = values.get(fieldname)
        if fieldname == "isolation_required":
            value = cint(value)
        doc.set(fieldname, value)
    doc.save()
    return _episode_payload(doc)


@frappe.whitelist()
def add_hospitalisation_activity(
    hospitalisation_name: str,
    activity_type: str,
    activity_datetime: str | None = None,
    clinical_notes: str | None = None,
    billable: int | str = 0,
    stock_affecting: int | str = 0,
    item: str | None = None,
    qty: float | str | None = None,
    uom: str | None = None,
    source_warehouse: str | None = None,
    modified: str | None = None,
) -> dict[str, Any]:
    doc = _load_hospitalisation(hospitalisation_name, write=True)
    _assert_not_stale(doc, modified)
    if _clean(doc.get("status")) in CLOSED_STATUSES:
        frappe.throw(_("Clinical activity cannot be added to a closed Hospitalisation."), frappe.ValidationError)

    resolved_type = _clean(activity_type) or "Other"
    if resolved_type not in ACTIVITY_TYPES:
        frappe.throw(_("Unsupported Hospitalisation activity type."), frappe.ValidationError)

    resolved_item = _clean(item)
    resolved_qty = flt(qty) if qty not in (None, "") else (1 if resolved_item else 0)
    if resolved_item and resolved_qty <= 0:
        frappe.throw(_("Quantity must be greater than zero when an Item is selected."), frappe.ValidationError)
    if resolved_item and not uom:
        uom = frappe.db.get_value("Item", resolved_item, "stock_uom")

    row = doc.append(
        "activities",
        {
            "activity_type": resolved_type,
            "activity_datetime": activity_datetime or now_datetime(),
            "performed_by": get_current_user(),
            "clinical_notes": clinical_notes,
            "billable": cint(billable),
            "stock_affecting": cint(stock_affecting),
            "item": resolved_item or None,
            "qty": resolved_qty or None,
            "uom": uom,
            "source_warehouse": source_warehouse,
        },
    )
    doc.save()
    return {
        "activity": _activity_payload(row),
        "episode": _episode_payload(doc),
        "warnings": [
            message
            for condition, message in (
                (cint(billable) and not resolved_item, _("Billable activity has no Item and cannot be converted to a charge until one is supplied.")),
                (cint(stock_affecting) and not resolved_item, _("Stock-affecting activity has no Item and cannot be posted until one is supplied.")),
            )
            if condition
        ],
    }


@frappe.whitelist()
def search_hospitalisation_episode_options(
    hospitalisation_name: str,
    field: str,
    txt: str = "",
    start: int | str = 0,
    page_length: int | str = 20,
) -> list[dict[str, Any]]:
    doc = _load_hospitalisation(hospitalisation_name)
    query = _clean(txt)
    page_len = _bounded_limit(page_length)
    try:
        offset = max(int(start or 0), 0)
    except (TypeError, ValueError):
        offset = 0

    if field == "care_location":
        filters: dict[str, Any] = {
            "enabled": 1,
            "branch": doc.get("service_branch"),
            "status": ["in", ["Available", "Occupied"]],
        }
        or_filters = None
        if query:
            or_filters = [
                [CARE_LOCATION_DOCTYPE, "name", "like", f"%{query}%"],
                [CARE_LOCATION_DOCTYPE, "location_name", "like", f"%{query}%"],
            ]
        rows = frappe.get_list(
            CARE_LOCATION_DOCTYPE,
            filters=filters,
            or_filters=or_filters,
            fields=["name", "location_name", "location_type", "status", "capacity"],
            order_by="location_name asc",
            start=offset,
            page_length=page_len,
        )
        return [
            {
                "value": row.get("name"),
                "label": row.get("location_name") or row.get("name"),
                "description": " · ".join(filter(None, [row.get("location_type"), row.get("status")])),
            }
            for row in rows
        ]

    if field == "item":
        filters = {"disabled": 0}
        or_filters = None
        if query:
            or_filters = [
                ["Item", "name", "like", f"%{query}%"],
                ["Item", "item_name", "like", f"%{query}%"],
            ]
        rows = frappe.get_list(
            "Item",
            filters=filters,
            or_filters=or_filters,
            fields=["name", "item_name", "stock_uom", "is_stock_item"],
            order_by="item_name asc",
            start=offset,
            page_length=page_len,
        )
        return [
            {
                "value": row.get("name"),
                "label": row.get("item_name") or row.get("name"),
                "description": " · ".join(filter(None, [row.get("stock_uom"), "Stock Item" if cint(row.get("is_stock_item")) else "Service Item"])),
                "uom": row.get("stock_uom"),
                "is_stock_item": cint(row.get("is_stock_item")),
            }
            for row in rows
        ]

    if field == "practitioner":
        rows = get_veterinary_doctor_users("User", query, "name", offset, page_len, {})
        return [{"value": row[0], "label": row[1]} for row in rows]

    frappe.throw(_("Unsupported Hospitalisation episode option field."), frappe.ValidationError)
