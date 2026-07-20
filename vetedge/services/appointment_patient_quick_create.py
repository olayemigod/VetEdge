from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cstr

from vetedge.coreedge_adapter import get_current_vetedge_branch
from vetedge.services.appointment_edgeui import (
	_clean,
	_find_patient_duplicate,
	_option,
	_owner_label,
	_parse_values,
)
from vetedge.services.company_context import validate_customer_company, validate_vetedge_company
from vetedge.services.permissions import can_access_branch_data


def _optional_text(payload: dict[str, Any], fieldname: str) -> str | None:
	value = cstr(payload.get(fieldname) or "").strip()
	return value or None


@frappe.whitelist()
def create_full_appointment_patient(values: str | dict) -> dict[str, Any]:
	"""Create an active Veterinary Patient from the EdgeSuite appointment flow.

	The endpoint accepts the complete set of editable registration fields while
	leaving registration billing fields under the existing server workflow.
	"""
	if frappe.session.user == "Guest":
		frappe.throw(_("Authentication required."), frappe.PermissionError)
	if not frappe.has_permission("Veterinary Patient", "create"):
		frappe.throw(_("You are not permitted to create Veterinary Patients."), frappe.PermissionError)
	if not frappe.db.has_column("Veterinary Patient", "company"):
		frappe.throw(
			_("VetEdge Company fields are not installed. Run bench migrate for this site."),
			frappe.ValidationError,
		)

	payload = _parse_values(values)
	company = validate_vetedge_company(payload.get("company"))
	patient_name = _clean(payload.get("patient_name"))
	owner = _clean(payload.get("primary_owner"))
	branch = _clean(payload.get("default_branch") or get_current_vetedge_branch())
	species = _clean(payload.get("species"))
	breed = _clean(payload.get("breed"))
	microchip_id = _clean(payload.get("microchip_id"))

	if not patient_name or not owner or not species:
		frappe.throw(_("Patient Name, Primary Owner and Species are required."), frappe.ValidationError)
	validate_customer_company(owner, company)
	if branch:
		can_access_branch_data(frappe.session.user, branch, raise_exception=True)
	if not frappe.db.exists("Veterinary Species", species):
		frappe.throw(_("Species is not valid."), frappe.ValidationError)
	if breed:
		breed_species = frappe.db.get_value("Veterinary Breed", breed, "species")
		if not breed_species or breed_species != species:
			frappe.throw(_("Breed must belong to the selected Species."), frappe.ValidationError)

	duplicate = _find_patient_duplicate(company, owner, patient_name, microchip_id)
	if duplicate:
		frappe.throw(
			_("A matching Veterinary Patient already exists: {0}").format(duplicate),
			frappe.DuplicateEntryError,
		)

	weight_baseline = payload.get("weight_baseline")
	if weight_baseline in ("", None):
		weight_baseline = None

	doc = frappe.get_doc(
		{
			"doctype": "Veterinary Patient",
			"patient_name": patient_name,
			"primary_owner": owner,
			"company": company,
			"default_branch": branch,
			"species": species,
			"breed": breed,
			"sex": _clean(payload.get("sex")),
			"neuter_status": _clean(payload.get("neuter_status")),
			"color_markings": _clean(payload.get("color_markings")),
			"microchip_id": microchip_id or None,
			"date_of_birth": _optional_text(payload, "date_of_birth"),
			"weight_baseline": weight_baseline,
			"emergency_contact": _clean(payload.get("emergency_contact")),
			"status": "Active",
			"is_deceased": 0,
		}
	)
	doc.insert()
	return _option(
		doc.name,
		doc.patient_name,
		" · ".join(filter(None, [_owner_label(doc.primary_owner), doc.species, doc.breed])),
		primary_owner=doc.primary_owner,
		primary_owner_label=_owner_label(doc.primary_owner),
		company=doc.company,
		default_branch=doc.default_branch,
	)
