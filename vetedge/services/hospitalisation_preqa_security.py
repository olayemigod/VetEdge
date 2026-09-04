from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr, now

from vetedge.services.hospitalisation_permissions import validate_hospitalisation_branch_access
from vetedge.services.permissions import (
    get_assigned_branches,
    is_internal_staff_user,
    is_portal_owner_user,
    user_has_global_branch_access,
)
from vetedge.services.portal_access import require_internal_user


HOSPITALISATION_DOCTYPE = "Veterinary Hospitalisation"
PATIENT_DOCTYPE = "Veterinary Patient"
CONSULTATION_DOCTYPE = "Veterinary Consultation"
CARE_LOCATION_DOCTYPE = "Veterinary Care Location"
CARE_LOCATION_LOG_DOCTYPE = "Veterinary Care Location Occupancy Log"
ACTIVE_CARE_LOCATION_HOSPITALISATION_STATUSES = {"Admitted", "Under Care", "Ready for Discharge"}
BLOCKED_CARE_LOCATION_STATUSES = {"Inactive", "Maintenance", "Cleaning"}
LINKED_RECORD_FIELDS = {
    "Veterinary Vital Signs": (
        "name",
        "recorded_on",
        "temperature",
        "weight",
        "heart_rate",
        "respiratory_rate",
        "body_condition_score",
        "hydration_status",
        "mucous_membrane",
        "capillary_refill_time",
        "pain_score",
        "appetite_status",
        "notes",
    ),
    "Veterinary Vaccination Record": (
        "name",
        "status",
        "vaccine",
        "administered_by",
        "administered_on",
        "dose",
        "route",
        "next_due_date",
        "expiry_date",
        "batch_no",
        "notes",
    ),
    "Veterinary Lab Order": (
        "name",
        "status",
        "order_date",
        "ordered_on",
        "sample_collected_on",
        "sample_notes",
        "notes",
    ),
}


def _clean(value) -> str:
    return cstr(value or "").strip()


def _current_user() -> str:
    return _clean(getattr(frappe.session, "user", None)) or "Guest"


def _load_hospitalisation(hospitalisation_name: str, *, write: bool = False):
    require_internal_user()
    name = _clean(hospitalisation_name)
    if not name:
        frappe.throw(_("Hospitalisation is required."), frappe.ValidationError)

    doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, name)
    doc.check_permission("write" if write else "read")
    validate_hospitalisation_branch_access(doc)
    return doc


def _assert_not_stale(doc, modified: str | None) -> None:
    if modified and cstr(doc.modified) != cstr(modified):
        frappe.throw(
            _("This Hospitalisation changed after the page was loaded. Refresh and try again."),
            frappe.TimestampMismatchError,
        )


def _assert_branch_visible(branch: str | None) -> None:
    require_internal_user()
    user = _current_user()
    if is_portal_owner_user(user) or not is_internal_staff_user(user):
        frappe.throw(_("This action is only available to authorised clinic staff."), frappe.PermissionError)
    if user_has_global_branch_access(user):
        return

    allowed = {_clean(value) for value in get_assigned_branches(user) if _clean(value)}
    if not allowed:
        frappe.throw(
            _("You do not have an assigned Veterinary Branch."),
            frappe.PermissionError,
        )

    selected = _clean(branch)
    if selected and selected not in allowed:
        frappe.throw(
            _("You do not have access to Veterinary Branch {0}.").format(selected),
            frappe.PermissionError,
        )


def _safe_doc_values(doctype: str, name: str | None, fields: tuple[str, ...]) -> dict:
    name = _clean(name)
    if not name or not frappe.db.exists(doctype, name):
        return {}
    meta = frappe.get_meta(doctype)
    available = [field for field in fields if field == "name" or meta.has_field(field)]
    if not available:
        return {"name": name}
    values = frappe.db.get_value(doctype, name, available, as_dict=True) or {}
    values.setdefault("name", name)
    return dict(values)


def _linked_record_field_rows(record, fields: tuple[str, ...]) -> list[dict]:
    meta = frappe.get_meta(record.doctype)
    rows = []
    for fieldname in fields:
        if fieldname == "name":
            rows.append({"fieldname": "name", "label": _("Record ID"), "value": record.name})
            continue
        field = meta.get_field(fieldname)
        if not field:
            continue
        value = record.get(fieldname)
        if value in (None, ""):
            continue
        rows.append({"fieldname": fieldname, "label": field.label or fieldname, "value": value})
    return rows


def _system_update_care_location_status(care_location: str) -> dict:
    """Update derived capacity status after the caller has passed Hospitalisation authorization."""
    from vetedge.services.hospitalisation import get_active_care_location_occupancy_count

    location = frappe.get_doc(CARE_LOCATION_DOCTYPE, care_location)
    capacity = max(cint(location.get("capacity")) or 1, 1)
    active_count = get_active_care_location_occupancy_count(care_location)
    if not cint(location.get("enabled")) or location.get("status") in BLOCKED_CARE_LOCATION_STATUSES:
        return {
            "care_location": care_location,
            "capacity": capacity,
            "active_occupancy_count": active_count,
            "available_slots": max(capacity - active_count, 0),
            "status": location.get("status"),
        }

    new_status = "Occupied" if active_count >= capacity else "Available"
    if location.get("status") != new_status:
        location.status = new_status
        # Care Location status is derived operational state. The user has already
        # passed Hospitalisation write permission and Branch validation above.
        location.save(ignore_permissions=True)
    return {
        "care_location": care_location,
        "capacity": capacity,
        "active_occupancy_count": active_count,
        "available_slots": max(capacity - active_count, 0),
        "status": new_status,
    }


@frappe.whitelist()
@frappe.read_only()
def get_hospitalisation_patient_snapshot(hospitalisation_name: str) -> dict:
    """Return the minimal read-only Patient/Owner identity for a visible episode.

    The Hospitalisation is the access authority. This avoids exposing a generic
    Patient or Customer lookup endpoint while still allowing Operations users to
    inspect the record without navigating away from the report.
    """
    doc = _load_hospitalisation(hospitalisation_name, write=False)
    patient = _safe_doc_values(
        PATIENT_DOCTYPE,
        doc.get("patient"),
        (
            "name",
            "patient_name",
            "species",
            "breed",
            "sex",
            "approximate_age",
            "date_of_birth",
            "primary_owner",
        ),
    )
    owner = _safe_doc_values(
        "Customer",
        doc.get("customer") or patient.get("primary_owner"),
        ("name", "customer_name", "mobile_no", "email_id", "customer_group", "territory"),
    )
    return {
        "hospitalisation": doc.name,
        "patient": patient,
        "owner": owner,
        "service_branch": doc.get("service_branch"),
        "company": doc.get("company"),
        "status": doc.get("status"),
        "admission_datetime": doc.get("admission_datetime"),
    }


@frappe.whitelist()
@frappe.read_only()
def get_hospitalisation_linked_record_snapshot(
    hospitalisation_name: str,
    linked_doctype: str,
    linked_document: str,
) -> dict:
    """Return bounded read-only detail for a clinical record linked to this episode."""
    doc = _load_hospitalisation(hospitalisation_name, write=False)
    doctype = _clean(linked_doctype)
    name = _clean(linked_document)
    fields = LINKED_RECORD_FIELDS.get(doctype)
    if not fields or not name:
        frappe.throw(_("This linked Hospitalisation record type is not available for contextual viewing."), frappe.ValidationError)

    linked_from_episode = any(
        _clean(row.get("linked_doctype")) == doctype and _clean(row.get("linked_document")) == name
        for row in doc.get("activities") or []
    )
    if not linked_from_episode:
        frappe.throw(_("The requested clinical record is not linked to this Hospitalisation."), frappe.PermissionError)
    if not frappe.db.exists(doctype, name):
        frappe.throw(_("The linked clinical record could not be found."), frappe.DoesNotExistError)

    record = frappe.get_doc(doctype, name)
    record.check_permission("read")
    meta = frappe.get_meta(doctype)
    title = record.get(meta.title_field) if meta.title_field and meta.has_field(meta.title_field) else None
    return {
        "hospitalisation": doc.name,
        "doctype": doctype,
        "name": name,
        "title": title or name,
        "fields": _linked_record_field_rows(record, fields),
    }


@frappe.whitelist()
@frappe.read_only()
def get_hospitalisation_operations(filters=None, start: int = 0, page_length: int = 50, sort=None) -> dict:
    """Preserve Operations data while keeping Branch informational, not a link."""
    from vetedge.services.hospitalisation_operations import get_hospitalisation_operations as original

    payload = original(filters=filters, start=start, page_length=page_length, sort=sort)
    for column in payload.get("columns") or []:
        if column.get("fieldname") == "branch":
            column["fieldtype"] = "Data"
            column.pop("options", None)
            column["clickable"] = False
    return payload


@frappe.whitelist()
@frappe.read_only()
def get_hospitalisation_patient_context(patient: str) -> dict:
    from vetedge.services.hospitalisation import get_hospitalisation_patient_context as original

    require_internal_user()
    patient_name = _clean(patient)
    patient_doc = frappe.get_doc(PATIENT_DOCTYPE, patient_name)
    patient_doc.check_permission("read")
    _assert_branch_visible(patient_doc.get("default_branch"))
    return original(patient_name)


@frappe.whitelist()
def create_hospitalisation_from_consultation(consultation_name: str) -> str:
    from vetedge.services.hospitalisation import create_hospitalisation_from_consultation as original

    require_internal_user()
    consultation = frappe.get_doc(CONSULTATION_DOCTYPE, _clean(consultation_name))
    consultation.check_permission("read")
    _assert_branch_visible(consultation.get("service_branch"))
    return original(consultation.name)


@frappe.whitelist()
@frappe.read_only()
def get_hospitalisation_medication_item_context(hospitalisation_name: str, item: str, uom: str | None = None) -> dict:
    from vetedge.services.hospitalisation import get_hospitalisation_medication_item_context as original

    _load_hospitalisation(hospitalisation_name, write=False)
    return original(hospitalisation_name, item, uom=uom)


@frappe.whitelist()
def build_hospitalisation_charge_items(hospitalisation_name: str) -> dict:
    from vetedge.services.hospitalisation import build_hospitalisation_charge_items as original

    _load_hospitalisation(hospitalisation_name, write=True)
    return original(hospitalisation_name)


@frappe.whitelist()
def create_or_link_hospitalisation_invoice(hospitalisation_name: str) -> str:
    from vetedge.services.hospitalisation import create_or_link_hospitalisation_invoice as original

    _load_hospitalisation(hospitalisation_name, write=True)
    return original(hospitalisation_name)


@frappe.whitelist()
def sync_hospitalisation_charges_to_invoice(
    hospitalisation_name: str,
    confirm: bool = False,
    confirmation_type: str | None = None,
) -> dict:
    from vetedge.services.hospitalisation import sync_hospitalisation_charges_to_invoice as original

    _load_hospitalisation(hospitalisation_name, write=True)
    return original(
        hospitalisation_name,
        confirm=confirm,
        confirmation_type=confirmation_type,
    )


@frappe.whitelist()
def assign_hospitalisation_care_location(
    hospitalisation_name: str,
    care_location: str,
    notes: str | None = None,
    modified: str | None = None,
) -> dict:
    from vetedge.services import hospitalisation as service

    doc = _load_hospitalisation(hospitalisation_name, write=True)
    _assert_not_stale(doc, modified)
    if doc.get("status") not in ACTIVE_CARE_LOCATION_HOSPITALISATION_STATUSES:
        frappe.throw(_("Care Location can only be assigned after the patient is admitted."), frappe.ValidationError)

    care_location = _clean(care_location)
    if not care_location or not frappe.db.exists(CARE_LOCATION_DOCTYPE, care_location):
        frappe.throw(_("Select a valid Veterinary Care Location."), frappe.ValidationError)
    location = frappe.get_doc(CARE_LOCATION_DOCTYPE, care_location)
    availability = service.ensure_care_location_assignable(doc, location)

    previous_location = _clean(doc.get("care_location"))
    if previous_location and previous_location != care_location:
        release_hospitalisation_care_location(
            hospitalisation_name,
            notes=_("Released before reassignment."),
            modified=modified,
        )
        doc = _load_hospitalisation(hospitalisation_name, write=True)

    assigned_on = now()
    doc.care_location = care_location
    doc.care_location_assigned_on = assigned_on
    doc.care_location_released_on = None
    doc.care_location_status = "Assigned"
    doc.save()

    log_name = service.get_active_care_location_log(doc.name, care_location)
    if log_name:
        log = frappe.get_doc(CARE_LOCATION_LOG_DOCTYPE, log_name)
        log.notes = notes or log.get("notes")
        # Occupancy history is system-maintained after the caller has passed
        # Hospitalisation write permission, Branch, availability and capacity checks.
        log.save(ignore_permissions=True)
    else:
        log = frappe.get_doc(
            {
                "doctype": CARE_LOCATION_LOG_DOCTYPE,
                "hospitalisation": doc.name,
                "patient": doc.get("patient"),
                "pet_owner": doc.get("customer") or doc.get("primary_owner"),
                "care_location": care_location,
                "branch": service.get_hospitalisation_branch(doc) or location.get("branch"),
                "assigned_on": assigned_on,
                "status": "Active",
                "assigned_by": frappe.session.user,
                "notes": notes,
            }
        )
        log.insert(ignore_permissions=True)

    status = _system_update_care_location_status(care_location)
    return {
        "hospitalisation": doc.name,
        "care_location": care_location,
        "assigned": True,
        "message": _("Care location assigned."),
        **availability,
        **status,
    }


@frappe.whitelist()
def release_hospitalisation_care_location(
    hospitalisation_name: str,
    notes: str | None = None,
    modified: str | None = None,
) -> dict:
    from vetedge.services import hospitalisation as service

    doc = _load_hospitalisation(hospitalisation_name, write=True)
    _assert_not_stale(doc, modified)
    care_location = _clean(doc.get("care_location"))
    if not care_location:
        return {
            "hospitalisation": doc.name,
            "released": False,
            "message": _("No care location is assigned."),
        }

    released_on = now()
    log_name = service.get_active_care_location_log(doc.name, care_location)
    if log_name:
        log = frappe.get_doc(CARE_LOCATION_LOG_DOCTYPE, log_name)
        log.status = "Released"
        log.released_on = released_on
        log.released_by = frappe.session.user
        log.notes = notes or log.get("notes")
        # Occupancy history cannot be edited directly by ordinary clinical users;
        # only this authorised workflow writes the audit state.
        log.save(ignore_permissions=True)

    doc.care_location_released_on = released_on
    doc.care_location_status = "Released"
    doc.care_location = None
    doc.save()
    status = _system_update_care_location_status(care_location)
    return {
        "hospitalisation": doc.name,
        "care_location": care_location,
        "released": True,
        "message": _("Care location released."),
        **status,
    }


@frappe.whitelist()
@frappe.read_only()
def get_available_care_locations(
    branch: str | None = None,
    location_type: str | None = None,
    care_level: str | None = None,
) -> list[dict]:
    from vetedge.services.hospitalisation import get_available_care_locations as original

    require_internal_user()
    requested_branch = _clean(branch)
    user = _current_user()
    if user_has_global_branch_access(user):
        return original(branch=requested_branch or None, location_type=location_type, care_level=care_level)

    allowed = sorted({_clean(value) for value in get_assigned_branches(user) if _clean(value)})
    if not allowed:
        frappe.throw(_("You do not have an assigned Veterinary Branch."), frappe.PermissionError)
    if requested_branch:
        _assert_branch_visible(requested_branch)
        return original(branch=requested_branch, location_type=location_type, care_level=care_level)

    rows: list[dict] = []
    seen: set[str] = set()
    for allowed_branch in allowed:
        for row in original(branch=allowed_branch, location_type=location_type, care_level=care_level):
            name = _clean(row.get("name"))
            if name and name not in seen:
                seen.add(name)
                rows.append(row)
    return rows