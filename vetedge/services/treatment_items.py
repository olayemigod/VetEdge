from __future__ import annotations

from dataclasses import dataclass

import frappe
from frappe.utils import cint, flt

from vetedge.services.portal_access import require_internal_user


TREATMENT_ITEM_DOCTYPE = "Veterinary Treatment Item"


@dataclass(frozen=True)
class TreatmentItemDefaults:
	item: str
	service_type: str | None
	treatment_type: str | None
	shelf_life_in_days: int


def get_treatment_item_defaults(item_code: str | None) -> TreatmentItemDefaults | None:
	if not item_code or not frappe.db.exists("DocType", TREATMENT_ITEM_DOCTYPE):
		return None

	profile = frappe.db.get_value(
		TREATMENT_ITEM_DOCTYPE,
		{"item": item_code, "disabled": 0},
		["item", "service_type", "treatment_type", "shelf_life_in_days"],
		as_dict=True,
	)
	if not profile:
		return None

	return TreatmentItemDefaults(
		item=profile.item,
		service_type=profile.service_type,
		treatment_type=profile.treatment_type,
		shelf_life_in_days=cint(profile.shelf_life_in_days or 0),
	)


def apply_planned_treatment_defaults(row) -> TreatmentItemDefaults | None:
	defaults = get_treatment_item_defaults(row.get("item"))
	if not defaults:
		return None

	if not row.get("service_type") and defaults.service_type:
		row.service_type = defaults.service_type
	if not row.get("treatment_type") and defaults.treatment_type:
		row.treatment_type = defaults.treatment_type

	return defaults


@frappe.whitelist()
def get_treatment_item_defaults_for_consultation(item_code: str) -> dict:
	require_internal_user()
	defaults = get_treatment_item_defaults(item_code)
	return {
		"item": defaults.item,
		"service_type": defaults.service_type,
		"treatment_type": defaults.treatment_type,
		"shelf_life_in_days": defaults.shelf_life_in_days,
	} if defaults else {}


def validate_treatment_item_profile(doc) -> None:
	item = frappe.db.get_value(
		"Item",
		doc.item,
		["disabled"],
		as_dict=True,
	)
	if not item:
		frappe.throw("Veterinary Treatment Item must reference a valid ERPNext Item.", frappe.ValidationError)
	if cint(item.disabled):
		frappe.throw("Veterinary Treatment Item cannot reference a disabled ERPNext Item.", frappe.ValidationError)

	validate_optional_link("Veterinary Service Type", doc.service_type, "Service Type")
	validate_optional_link("Veterinary Treatment Type", doc.treatment_type, "Treatment Type")
	if cint(doc.shelf_life_in_days) < 0:
		frappe.throw("Shelf Life in Days cannot be negative.", frappe.ValidationError)
	if doc.get("default_price") not in (None, "") and flt(doc.get("default_price")) < 0:
		frappe.throw("Default Price cannot be negative.", frappe.ValidationError)
	if cint(doc.shelf_life_in_days) > 0:
		sync_item_shelf_life(doc.item, cint(doc.shelf_life_in_days))


def validate_optional_link(doctype: str, name: str | None, label: str) -> None:
	if not name:
		return

	if not frappe.db.exists(doctype, name):
		frappe.throw(f"{label} must reference a valid {doctype}.", frappe.ValidationError)
	if frappe.get_meta(doctype).has_field("disabled") and frappe.db.get_value(doctype, name, "disabled"):
		frappe.throw(f"{label} cannot reference a disabled {doctype}.", frappe.ValidationError)


def sync_item_shelf_life(item_code: str, shelf_life_in_days: int) -> None:
	item_meta = frappe.get_meta("Item")
	if not item_meta.has_field("shelf_life_in_days"):
		return

	frappe.db.set_value(
		"Item",
		item_code,
		"shelf_life_in_days",
		shelf_life_in_days,
		update_modified=False,
	)
