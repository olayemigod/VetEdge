from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from vetedge.services.age import calculate_age_label
from vetedge.services.company_context_compat import get_branch_company
from vetedge.services.registration_billing import validate_patient_registration


def validate_patient(doc) -> None:
	normalize_patient_fields(doc)
	validate_patient_company_context(doc)
	validate_birth_date(doc)
	validate_weight(doc)
	validate_breed_species(doc)
	sync_deceased_status(doc)
	validate_patient_registration(doc)


def normalize_patient_fields(doc) -> None:
	doc.patient_name = (doc.patient_name or "").strip()
	if not doc.get("default_branch") and doc.get("branch"):
		doc.default_branch = doc.branch
	if not doc.get("default_branch"):
		try:
			from vetedge.services.branch_context import get_working_branch_name

			doc.default_branch = get_working_branch_name() or None
		except (ImportError, ModuleNotFoundError, RuntimeError):
			pass
	if not doc.get("company") and doc.get("default_branch"):
		doc.company = get_branch_company(doc.default_branch) or None
	if not doc.get("company"):
		try:
			from vetedge.services.branch_context import get_working_company

			doc.company = get_working_company() or None
		except (ImportError, ModuleNotFoundError, RuntimeError):
			pass
	doc.color_markings = (doc.color_markings or "").strip()
	doc.microchip_id = (doc.microchip_id or "").strip() or None
	doc.emergency_contact = (doc.emergency_contact or "").strip()


def validate_patient_company_context(doc) -> None:
	if not doc.get("company"):
		frappe.throw(
			_("Select a Veterinary Company or configure the patient's Default Branch with a Veterinary Company."),
			frappe.ValidationError,
		)
	if not doc.get("default_branch"):
		return
	branch_company = get_branch_company(doc.default_branch)
	if branch_company and branch_company != doc.company:
		frappe.throw(
			_("Default Branch {0} belongs to Company {1}, not Company {2}.").format(
				doc.default_branch,
				branch_company,
				doc.company,
			),
			frappe.ValidationError,
		)


def validate_birth_date(doc) -> None:
	if doc.date_of_birth and getdate(doc.date_of_birth) > getdate(nowdate()):
		frappe.throw("Date of Birth cannot be in the future.", frappe.ValidationError)

	doc.approximate_age = calculate_age_label(doc.date_of_birth)


def validate_weight(doc) -> None:
	if doc.weight_baseline in (None, ""):
		return

	if flt(doc.weight_baseline) < 0:
		frappe.throw("Baseline Weight cannot be negative.", frappe.ValidationError)


def validate_breed_species(doc) -> None:
	if not doc.breed or not doc.species:
		return

	breed_species = frappe.db.get_value("Veterinary Breed", doc.breed, "species")
	if breed_species and breed_species != doc.species:
		frappe.throw("Breed must belong to the selected Species.", frappe.ValidationError)


def sync_deceased_status(doc) -> None:
	if doc.is_deceased:
		doc.status = "Deceased"
	elif doc.status == "Deceased":
		doc.is_deceased = 1
