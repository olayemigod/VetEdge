from __future__ import annotations

import frappe
from frappe.utils import cint, flt, getdate, nowdate

from vetedge.services.age import calculate_age_label
from vetedge.services.registration_billing import validate_patient_registration


def validate_patient(doc) -> None:
	normalize_patient_fields(doc)
	validate_birth_date(doc)
	validate_weight(doc)
	validate_breed_species(doc)
	sync_deceased_status(doc)
	validate_patient_registration(doc)


def normalize_patient_fields(doc) -> None:
	doc.patient_name = (doc.patient_name or "").strip()
	if not doc.get("default_branch") and doc.get("branch"):
		doc.default_branch = doc.branch
	doc.color_markings = (doc.color_markings or "").strip()
	doc.microchip_id = (doc.microchip_id or "").strip() or None
	doc.emergency_contact = (doc.emergency_contact or "").strip()


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
	"""Keep Status and Is Deceased synchronized without trapping corrections.

	New Patients always enter the system as living/Active. A historical Patient can
	later be marked deceased, and an authorized correction can clear the deceased
	flag again. The service guard separately prevents new clinical services for a
	Patient while the deceased state is active.
	"""
	previous = doc.get_doc_before_save() if getattr(doc, "get_doc_before_save", None) else None
	is_new_method = getattr(doc, "is_new", None)
	is_new = bool(is_new_method()) if callable(is_new_method) else previous is None

	if is_new and previous is None:
		doc.is_deceased = 0
		if doc.status == "Deceased" or not doc.status:
			doc.status = "Active"
		return

	current_flag = cint(doc.get("is_deceased"))
	previous_flag = cint(previous.get("is_deceased")) if previous else 0
	current_status = str(doc.get("status") or "Active")
	previous_status = str(previous.get("status") or "") if previous else ""

	if current_flag != previous_flag:
		if current_flag:
			doc.status = "Deceased"
		elif current_status == "Deceased":
			doc.status = "Active"
		return

	if current_status != previous_status:
		doc.is_deceased = 1 if current_status == "Deceased" else 0
		return

	if current_flag:
		doc.status = "Deceased"
	elif current_status == "Deceased":
		doc.status = "Active"
