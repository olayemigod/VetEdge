from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr

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
) -> dict:
    from vetedge.services.hospitalisation import assign_hospitalisation_care_location as original

    doc = _load_hospitalisation(hospitalisation_name, write=True)
    location = frappe.db.get_value(
        CARE_LOCATION_DOCTYPE,
        _clean(care_location),
        ["name", "branch", "enabled", "status"],
        as_dict=True,
    ) or {}
    if not location:
        frappe.throw(_("Select a valid Veterinary Care Location."), frappe.ValidationError)
    if _clean(location.get("branch")) and _clean(location.get("branch")) != _clean(doc.get("service_branch")):
        frappe.throw(_("Care Location Branch must match the Hospitalisation Branch."), frappe.ValidationError)
    if not cint(location.get("enabled")) or location.get("status") in {"Inactive", "Maintenance", "Cleaning"}:
        frappe.throw(_("Selected Care Location is not available for assignment."), frappe.ValidationError)
    return original(hospitalisation_name, care_location, notes=notes)


@frappe.whitelist()
def release_hospitalisation_care_location(hospitalisation_name: str, notes: str | None = None) -> dict:
    from vetedge.services.hospitalisation import release_hospitalisation_care_location as original

    _load_hospitalisation(hospitalisation_name, write=True)
    return original(hospitalisation_name, notes=notes)


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
