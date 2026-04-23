from __future__ import annotations

import frappe


SETTINGS_DOCTYPE = "Veterinary Settings"
DEFAULT_BRAND_NAME = "VetEdge"


def get_clinic_brand_name(fallback: str = DEFAULT_BRAND_NAME) -> str:
	brand_name = get_portal_brand_name()
	if brand_name:
		return brand_name

	company_name = get_default_company_name()
	if company_name:
		return company_name

	return fallback


def get_owner_portal_brand_name() -> str:
	return get_clinic_brand_name()


def get_portal_brand_name() -> str | None:
	try:
		if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
			return None

		meta = frappe.get_meta(SETTINGS_DOCTYPE)
		if not meta.has_field("portal_brand_name"):
			return None

		settings = frappe.get_single(SETTINGS_DOCTYPE)
		return (settings.get("portal_brand_name") or "").strip() or None
	except Exception:
		return None


def get_default_company_name() -> str | None:
	try:
		from vetedge.services.registration_billing import get_default_company

		company = get_default_company()
		if not company:
			return None

		return (
			frappe.db.get_value("Company", company, "company_name")
			or frappe.db.get_value("Company", company, "abbr")
			or company
		)
	except Exception:
		return None
