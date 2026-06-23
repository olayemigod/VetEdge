# -*- coding: utf-8 -*-
from __future__ import annotations

import frappe
from frappe import _

# Safe defaults
SAFE_DEFAULTS = {
	"enabled": 0,
	"brand_name": "VetEdge",
	"company_name": "VetEdge",
	"short_name": "VetEdge",
	"module_label": "Veterinary",
	"app_title": "VetEdge",
	"hide_source_product_name": 0,
	"logo": "",
	"favicon": "",
	"primary_color": "",
	"support_email": "",
	"support_phone": "",
	"source": "default"
}

def get_branding() -> dict:
	"""
	Resolves branding settings in order:
	1. CoreEdge API (if installed and active profile exists)
	2. site_config (frappe.conf) fallback keys
	3. Safe defaults
	
	An active CoreEdge branding profile takes priority and cannot be overridden by site_config.
	"""
	# 1. CoreEdge Integration
	try:
		from vetedge.coreedge_adapter import is_coreedge_available, is_coreedge_enabled, _parse_config_bool
		ce_available = is_coreedge_available()
		ce_enabled = is_coreedge_enabled()
	except Exception:
		ce_available = False
		ce_enabled = False
		_parse_config_bool = lambda val: bool(val)

	if ce_available and ce_enabled:
		try:
			get_product_branding = frappe.get_attr("coreedge.services.branding.get_product_branding")
			site = getattr(frappe.local, "site", None)
			ce_branding = get_product_branding(product_app="vetedge", tenant_site=site)
			
			if ce_branding and ce_branding.get("enabled"):
				return {
					"enabled": 1,
					"brand_name": ce_branding.get("brand_name") or "VetEdge",
					"company_name": ce_branding.get("company_name") or "VetEdge",
					"short_name": ce_branding.get("short_name") or "VetEdge",
					"module_label": ce_branding.get("module_label") or "Veterinary",
					"app_title": ce_branding.get("app_title") or "VetEdge",
					"logo": ce_branding.get("logo") or "",
					"favicon": ce_branding.get("favicon") or "",
					"primary_color": ce_branding.get("primary_color") or "",
					"support_email": ce_branding.get("support_email") or "",
					"support_phone": ce_branding.get("support_phone") or "",
					"hide_source_product_name": 1 if ce_branding.get("hide_source_product_name") else 0,
					"source": "coreedge"
				}
		except Exception as e:
			try:
				frappe.logger("vetedge").warning(f"Failed to resolve CoreEdge branding: {str(e)}")
			except Exception:
				pass

	# 2. site_config fallback
	try:
		sc_enabled = frappe.conf.get("vetedge_white_label_enabled")
		if _parse_config_bool(sc_enabled):
			return {
				"enabled": 1,
				"brand_name": frappe.conf.get("vetedge_brand_name") or "VetEdge",
				"company_name": frappe.conf.get("vetedge_company_name") or "VetEdge",
				"short_name": frappe.conf.get("vetedge_short_name") or "VetEdge",
				"module_label": frappe.conf.get("vetedge_module_label") or "Veterinary",
				"app_title": frappe.conf.get("vetedge_app_title") or "VetEdge",
				"logo": frappe.conf.get("vetedge_logo") or "",
				"favicon": frappe.conf.get("vetedge_favicon") or "",
				"primary_color": frappe.conf.get("vetedge_primary_color") or "",
				"support_email": frappe.conf.get("vetedge_support_email") or "",
				"support_phone": frappe.conf.get("vetedge_support_phone") or "",
				"hide_source_product_name": 1 if _parse_config_bool(frappe.conf.get("vetedge_hide_vetedge_name")) else 0,
				"source": "site_config"
			}
	except Exception as e:
		try:
			frappe.logger("vetedge").warning(f"Failed to resolve site_config branding: {str(e)}")
		except Exception:
			pass

	# 3. Safe Defaults
	return SAFE_DEFAULTS.copy()

def get_brand_name() -> str:
	return get_branding().get("brand_name")

def get_company_name() -> str:
	return get_branding().get("company_name")

def get_short_name() -> str:
	return get_branding().get("short_name")

def get_module_label() -> str:
	return get_branding().get("module_label")

def get_app_title() -> str:
	return get_branding().get("app_title")

def hide_source_product_name() -> bool:
	return bool(get_branding().get("hide_source_product_name"))

def replace_brand_tokens(text: str) -> str:
	"""
	Replaces user-facing brand tokens "VetEdge" and "VETEDGE" with resolved branding values.
	Does not blindly replace lowercase technical "vetedge" references.
	"""
	if not isinstance(text, str):
		return text

	brand_name = get_brand_name() or "VetEdge"

	text = text.replace("VetEdge", brand_name)
	text = text.replace("VETEDGE", brand_name.upper())
	return text

def get_clinic_brand_name() -> str:
	"""
	Returns the resolved clinic brand name.
	For backward compatibility, falls back to the old database/ERPNext checks if white-labeling is disabled.
	"""
	branding = get_branding()
	if branding.get("enabled"):
		return branding.get("brand_name") or "VetEdge"
		
	try:
		if frappe.db.exists("DocType", "Veterinary Settings"):
			settings = frappe.get_single("Veterinary Settings")
			meta = frappe.get_meta("Veterinary Settings")
			if meta.has_field("portal_brand_name") and settings.get("portal_brand_name"):
				return settings.get("portal_brand_name")
			if meta.has_field("clinic_brand_name") and settings.get("clinic_brand_name"):
				return settings.get("clinic_brand_name")
	except Exception:
		pass
		
	try:
		from vetedge.services.registration_billing import get_default_company
		company = get_default_company()
		if company:
			name = frappe.db.get_value("Company", company, "company_name")
			if name:
				return name
	except Exception:
		pass
		
	return "VetEdge"

def get_owner_portal_brand_name() -> str:
	"""
	Returns the resolved owner portal brand name.
	"""
	branding = get_branding()
	if branding.get("enabled"):
		return branding.get("brand_name") or "VetEdge"
		
	try:
		if frappe.db.exists("DocType", "Veterinary Settings"):
			settings = frappe.get_single("Veterinary Settings")
			meta = frappe.get_meta("Veterinary Settings")
			if meta.has_field("portal_brand_name") and settings.get("portal_brand_name"):
				return settings.get("portal_brand_name")
	except Exception:
		pass
		
	return "Owner Portal"
