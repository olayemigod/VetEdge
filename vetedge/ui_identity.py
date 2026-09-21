from __future__ import annotations

import frappe

from vetedge.coreedge_adapter import get_current_vetedge_company, get_edge_platform_mode
from vetedge.services.branding import get_branding

VETEDGE_LOGO = "/assets/vetedge/images/vetedge-app-icon.png"
MEDICAL_HISTORY_PAGE = "veterinary-medical-history"
EDGE_PAGE_DESTINATIONS = {
	"Veterinary Care Location": "vetedge-care-locations",
	"Branch User Assignment": "vetedge-branch-user-access",
	"Branch Practitioner Assignment": "vetedge-practitioner-coverage",
	"Veterinary Notification Preference": "vetedge-notification-preferences",
	"Veterinary Notification Log": "vetedge-notification-delivery-log",
	"Veterinary Notification Item": "vetedge-notification-items",
	"Veterinary Role Bundle": "vetedge-role-bundles",
	"Veterinary License Profile": "vetedge-license-profile",
}


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


def _settings_brand_identity() -> dict:
	"""Read clinic identity configured in the Veterinary Settings branding tab."""
	try:
		if not frappe.db.exists("DocType", "Veterinary Settings"):
			return {"name": "", "logo": ""}
		settings = frappe.get_single("Veterinary Settings")
		meta = frappe.get_meta("Veterinary Settings")
		return {
			"name": settings.get("portal_brand_name") if meta.has_field("portal_brand_name") else "",
			"logo": settings.get("portal_logo") if meta.has_field("portal_logo") else "",
		}
	except Exception:
		# Boot must remain available during install and schema migration.
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


def _expose_medical_history_page(bootinfo) -> None:
	"""Keep the permission-aware Medical History page discoverable in Frappe desk search."""
	page_info = bootinfo.get("page_info") or {}
	current = page_info.get(MEDICAL_HISTORY_PAGE) or {}
	page_info[MEDICAL_HISTORY_PAGE] = {
		**current,
		"title": "Medical History",
		"route": MEDICAL_HISTORY_PAGE,
	}
	bootinfo["page_info"] = page_info


def _align_edge_sidebar_destinations(bootinfo) -> None:
	"""Keep product navigation on EdgeSuite pages without changing stored DocType identity.

	The canonical Workspace Sidebar remains the source of labels, roles and ordering. Only
	the browser destination is adapted after permission filtering has already happened.
	This also keeps the shared product/waffle menu aligned because it consumes the same
	boot sidebar manifest.
	"""
	sidebars = bootinfo.get("workspace_sidebar_item") or {}
	for key in ("vetedge", "veterinary"):
		sidebar = sidebars.get(key)
		if not isinstance(sidebar, dict):
			continue
		for item in sidebar.get("items") or []:
			if not isinstance(item, dict) or item.get("type") != "Link":
				continue
			page = EDGE_PAGE_DESTINATIONS.get(item.get("link_to"))
			if not page:
				continue
			item["link_type"] = "Page"
			item["link_to"] = page
			item.pop("report", None)
	bootinfo["workspace_sidebar_item"] = sidebars


def build_vetedge_ui_identity() -> dict:
	branding = get_branding()
	mode = get_edge_platform_mode()
	company = _company_identity(_fallback_company())
	settings_brand = _settings_brand_identity()

	if branding.get("source") == "coreedge" and branding.get("enabled"):
		tenant_name = branding.get("company_name") or branding.get("brand_name") or company.get("label")
		tenant_logo = branding.get("logo") or settings_brand.get("logo") or company.get("logo") or ""
	else:
		tenant_name = settings_brand.get("name") or company.get("label") or branding.get("company_name") or branding.get("brand_name")
		tenant_logo = settings_brand.get("logo") or branding.get("logo") or company.get("logo") or ""

	tenant_name = tenant_name or "Veterinary Clinic"
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
	_expose_medical_history_page(bootinfo)
	_align_edge_sidebar_destinations(bootinfo)
