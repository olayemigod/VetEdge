from __future__ import annotations

import frappe

from vetedge.coreedge_adapter import get_current_vetedge_company, get_edge_platform_mode
from vetedge.services.branding import get_branding

VETEDGE_LOGO = "/assets/vetedge/images/vetedge-app-icon.png"


def _company_identity(company: str | None) -> dict:
	if not company or not frappe.db.exists("Company", company):
		return {"name": company or "", "label": company or "", "logo": ""}

	fields = ["name", "company_name"]
	meta = frappe.get_meta("Company")
	if meta.has_field("company_logo"):
		fields.append("company_logo")
	row = frappe.db.get_value("Company", company, fields, as_dict=True) or {}
	return {
		"name": row.get("name") or company,
		"label": row.get("company_name") or row.get("name") or company,
		"logo": row.get("company_logo") or "",
	}


def _settings_identity() -> dict:
	"""Resolve tenant-facing branding saved in Veterinary Settings.

	The existing ``portal_logo`` field is also the local clinic-logo fallback for
	operational EdgeSuite pages. This keeps one uploaded clinic identity across
	Desk and the owner portal without adding a second competing logo setting.
	"""
	try:
		if not frappe.db.exists("DocType", "Veterinary Settings"):
			return {"name": "", "logo": ""}
		meta = frappe.get_meta("Veterinary Settings")
		settings = frappe.get_single("Veterinary Settings")
		return {
			"name": settings.get("portal_brand_name") if meta.has_field("portal_brand_name") else "",
			"logo": settings.get("portal_logo") if meta.has_field("portal_logo") else "",
		}
	 except Exception:
		return {"name": "", "logo": ""}


def _fallback_company() -> str | None:
	try:
		return get_current_vetedge_company()
	except Exception:
		pass
	try:
		import erpnext

		return erpnext.get_default_company()
	except Exception:
		return frappe.db.get_value("Company", {}, "name")


def build_vetedge_ui_identity() -> dict:
	branding = get_branding()
	mode = get_edge_platform_mode()
	company = _company_identity(_fallback_company())
	settings = _settings_identity()

	tenant_name = company.get("label") or settings.get("name") or branding.get("company_name") or branding.get("brand_name") or "Veterinary Clinic"
	tenant_logo = settings.get("logo") or company.get("logo") or branding.get("logo") or ""

	is_saas = mode == "shared_hosted"
	product_name = "VetEdge" if is_saas else "Veterinary"
	product_logo = VETEDGE_LOGO if is_saas else ""

	return {
		"tenant_name": tenant_name,
		"tenant_logo": tenant_logo,
		"tenant_icon": "building",
		"tenant_subtitle": "Veterinary clinic workspace",
		"product_name": product_name,
		"product_logo": product_logo,
		"product_icon": "stethoscope",
		"product_subtitle": "Veterinary Practice Management",
		"deployment_mode": mode,
		"distribution": "vetedge" if is_saas else "veterinary",
	}


def extend_bootinfo(bootinfo) -> None:
	if frappe.session.user == "Guest":
		return

	try:
		identity = build_vetedge_ui_identity()
	except Exception:
		# Boot must remain usable during migrations and first-time setup.
		identity = {
			"tenant_name": "Veterinary Clinic",
			"tenant_logo": "",
			"tenant_icon": "building",
			"tenant_subtitle": "Veterinary clinic workspace",
			"product_name": "Veterinary",
			"product_logo": "",
			"product_icon": "stethoscope",
			"product_subtitle": "Veterinary Practice Management",
			"deployment_mode": "standalone",
			"distribution": "veterinary",
		}

	shared = bootinfo.get("edgesuite_ui_identity") or {}
	shared["vetedge"] = identity
	shared["veterinary"] = identity
	bootinfo["edgesuite_ui_identity"] = shared
	bootinfo["vetedge_ui_identity"] = identity
