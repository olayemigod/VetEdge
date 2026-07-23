from __future__ import annotations

import frappe

from vetedge.coreedge_adapter import get_current_vetedge_company, get_edge_platform_mode
from vetedge.services.branding import get_branding

# CoreEdge must expose an explicit product-logo URL. Deliberately do not consume
# a generic `logo` key because that may represent tenant or white-label branding.
COREDGE_PRODUCT_LOGO_KEYS = (
	"product_logo_url",
	"product_app_logo_url",
	"app_logo_url",
)


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


def _owner_portal_identity() -> dict:
	"""Resolve tenant-owned branding used only by owner-facing portal surfaces."""
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


def _coreedge_product_logo_url(mode: str) -> str:
	"""Resolve the ProcessEdge product logo for shared-hosted deployments only.

	Standalone and white-label deployments intentionally return an empty URL so
	the EdgeSuite shell renders its generic Veterinary product mark. The future
	remote CoreEdge service should expose one of ``COREDGE_PRODUCT_LOGO_KEYS``.
	"""
	if mode != "shared_hosted":
		return ""

	try:
		get_product_branding = frappe.get_attr("coreedge.services.branding.get_product_branding")
		payload = get_product_branding(
			product_app="vetedge",
			tenant_site=getattr(frappe.local, "site", None),
		) or {}
		for key in COREDGE_PRODUCT_LOGO_KEYS:
			value = payload.get(key)
			if value:
				return str(value).strip()
	except Exception:
		# Product identity must never prevent Desk boot. Until the remote CoreEdge
		# contract is available, the shell safely falls back to the generic mark.
		pass
	return ""


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
	owner_portal = _owner_portal_identity()

	tenant_name = (
		company.get("label")
		or owner_portal.get("name")
		or branding.get("company_name")
		or branding.get("brand_name")
		or "Veterinary Clinic"
	)
	owner_portal_logo = owner_portal.get("logo") or ""

	is_shared_hosted = mode == "shared_hosted"
	product_name = "VetEdge" if is_shared_hosted else "Veterinary"
	product_logo = _coreedge_product_logo_url(mode)

	return {
		"tenant_name": tenant_name,
		# Tenant/owner logo is retained for owner-facing consumers only. The
		# operational shell must use product_logo, never tenant_logo.
		"tenant_logo": owner_portal_logo,
		"owner_portal_logo": owner_portal_logo,
		"tenant_logo_scope": "owner_portal",
		"tenant_icon": "building",
		"tenant_subtitle": "Veterinary clinic workspace",
		"product_name": product_name,
		"product_logo": product_logo,
		"product_logo_source": "coreedge" if product_logo else "generic",
		"product_logo_scope": "operational_shell",
		"product_icon": "stethoscope",
		"product_subtitle": "Veterinary Practice Management",
		"deployment_mode": mode,
		"distribution": "vetedge" if is_shared_hosted else "veterinary",
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
			"owner_portal_logo": "",
			"tenant_logo_scope": "owner_portal",
			"tenant_icon": "building",
			"tenant_subtitle": "Veterinary clinic workspace",
			"product_name": "Veterinary",
			"product_logo": "",
			"product_logo_source": "generic",
			"product_logo_scope": "operational_shell",
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
