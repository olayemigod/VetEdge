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
	price_list: str | None = None
	default_price: float | None = None
	rate: float = 0
	uom: str | None = None


def get_treatment_item_defaults(item_code: str | None) -> TreatmentItemDefaults | None:
	if not item_code or not frappe.db.exists("DocType", TREATMENT_ITEM_DOCTYPE):
		return None

	profile = frappe.db.get_value(
		TREATMENT_ITEM_DOCTYPE,
		{"item": item_code, "disabled": 0},
		["item", "service_type", "treatment_type", "shelf_life_in_days", "price_list", "default_price"],
		as_dict=True,
	)
	if not profile:
		return None

	return TreatmentItemDefaults(
		item=profile.item,
		service_type=profile.service_type,
		treatment_type=profile.treatment_type,
		shelf_life_in_days=cint(profile.shelf_life_in_days or 0),
		price_list=profile.get("price_list") if hasattr(profile, "get") else getattr(profile, "price_list", None),
		default_price=profile.get("default_price") if hasattr(profile, "get") else getattr(profile, "default_price", None),
	)


def apply_planned_treatment_defaults(
	row,
	*,
	company: str | None = None,
	customer: str | None = None,
	branch: str | None = None,
) -> TreatmentItemDefaults | None:
	defaults = get_treatment_item_defaults(row.get("item"))
	if not defaults:
		defaults = get_planned_treatment_item_billing_defaults(row.get("item"), company=company, customer=customer, branch=branch)
		if not defaults:
			return None
	else:
		defaults = get_planned_treatment_item_billing_defaults(row.get("item"), company=company, customer=customer, branch=branch) or defaults

	if not row.get("service_type") and defaults.service_type:
		row.service_type = defaults.service_type
	if not row.get("treatment_type") and defaults.treatment_type:
		row.treatment_type = defaults.treatment_type
	if not row.get("uom") and defaults.uom:
		row.uom = defaults.uom
	if row.get("rate") in (None, ""):
		row.rate = flt(defaults.rate)

	return defaults


def get_planned_treatment_item_billing_defaults(
	item_code: str | None,
	*,
	company: str | None = None,
	customer: str | None = None,
	branch: str | None = None,
) -> TreatmentItemDefaults | None:
	if not item_code:
		return None
	defaults = get_treatment_item_defaults(item_code)
	item = frappe.db.get_value("Item", item_code, ["stock_uom", "standard_rate"], as_dict=True) or {}
	master_price_list = getattr(defaults, "price_list", None) if defaults else None
	rate = flt(getattr(defaults, "default_price", 0) if defaults else 0)
	if rate <= 0:
		try:
			from vetedge.services.billing_core import _get_item_selling_rate

			rate = flt(
				_get_item_selling_rate(
					item_code,
					company=company,
					customer=customer,
					branch=branch,
					uom=item.get("stock_uom"),
					master_price_list=master_price_list,
				)
			)
		except Exception:
			rate = flt(item.get("standard_rate"))
	if defaults:
		return TreatmentItemDefaults(
			item=getattr(defaults, "item", item_code),
			service_type=getattr(defaults, "service_type", None),
			treatment_type=getattr(defaults, "treatment_type", None),
			shelf_life_in_days=getattr(defaults, "shelf_life_in_days", 0),
			price_list=getattr(defaults, "price_list", None),
			default_price=getattr(defaults, "default_price", None),
			rate=rate,
			uom=item.get("stock_uom"),
		)
	return TreatmentItemDefaults(
		item=item_code,
		service_type=None,
		treatment_type=None,
		shelf_life_in_days=0,
		rate=rate,
		uom=item.get("stock_uom"),
	)


@frappe.whitelist()
def get_treatment_item_defaults_for_consultation(
	item_code: str,
	company: str | None = None,
	customer: str | None = None,
	branch: str | None = None,
) -> dict:
	require_internal_user()
	defaults = get_planned_treatment_item_billing_defaults(item_code, company=company, customer=customer, branch=branch)
	return {
		"item": defaults.item,
		"service_type": defaults.service_type,
		"treatment_type": defaults.treatment_type,
		"shelf_life_in_days": defaults.shelf_life_in_days,
		"uom": defaults.uom,
		"rate": defaults.rate,
		"amount": defaults.rate,
	} if defaults else {}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_treatment_item_link_options(doctype, txt, searchfield, start, page_len, filters):
	"""Return ERPNext Items curated through active Veterinary Treatment Item masters."""
	require_internal_user()
	if not frappe.db.exists("DocType", TREATMENT_ITEM_DOCTYPE):
		return []

	search = f"%{txt or ''}%"
	return frappe.db.sql(
		"""
		SELECT item.name, COALESCE(item.item_name, item.name)
		FROM `tabVeterinary Treatment Item` treatment
		INNER JOIN `tabItem` item ON item.name = treatment.item
		WHERE IFNULL(treatment.disabled, 0) = 0
			AND IFNULL(item.disabled, 0) = 0
			AND (
				item.name LIKE %(search)s
				OR item.item_name LIKE %(search)s
				OR treatment.name LIKE %(search)s
			)
		ORDER BY treatment.modified DESC, item.item_name ASC, item.name ASC
		LIMIT %(page_len)s OFFSET %(start)s
		""",
		{
			"search": search,
			"page_len": cint(page_len) or 20,
			"start": cint(start),
		},
	)


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
