# -*- coding: utf-8 -*-
from __future__ import annotations

import frappe
from frappe import _

def is_coreedge_available() -> bool:
	try:
		return "coreedge" in frappe.get_installed_apps()
	except Exception:
		return False

def is_coreedge_enabled() -> bool:
	try:
		return bool(frappe.db.get_single_value("Veterinary Settings", "enable_coreedge_platform"))
	except Exception:
		return False

def should_show_coreedge_controls() -> bool:
	return is_coreedge_available() and is_coreedge_enabled()

def get_vetedge_product_app() -> str:
	try:
		val = frappe.db.get_single_value("Veterinary Settings", "coreedge_product_app")
		return val or "VetEdge"
	except Exception:
		return "VetEdge"

def _get_local_fallback_context(user: str | None = None) -> dict:
	resolved_user = user or frappe.session.user
	default_company = None
	try:
		import erpnext
		default_company = erpnext.get_default_company()
	except Exception:
		pass
	if not default_company:
		try:
			default_company = frappe.db.get_value("Company", {}, "name")
		except Exception:
			pass
	
	product_app = get_vetedge_product_app()
	return {
		"user": resolved_user,
		"tenant": None,
		"product_app": product_app,
		"active_product_app": product_app,
		"branch": None,
		"active_branch": None,
		"company": default_company,
		"active_company": default_company,
		"allowed_companies": [default_company] if default_company else [],
		"allowed_branches": [],
		"available_product_apps": [product_app],
		"warnings": [],
		"blockers": [],
	}

def get_current_vetedge_context(user: str | None = None) -> dict:
	if not should_show_coreedge_controls():
		return _get_local_fallback_context(user)
	try:
		from coreedge.adapters.context import get_current_context
		return get_current_context(user=user)
	except (ImportError, ModuleNotFoundError):
		return _get_local_fallback_context(user)

def get_current_vetedge_branch(user: str | None = None) -> str | None:
	return get_current_vetedge_context(user).get("active_branch")

def get_current_vetedge_company(user: str | None = None) -> str | None:
	return get_current_vetedge_context(user).get("active_company")

def has_vetedge_access(product_app: str | None = None, tenant: str | None = None, user: str | None = None) -> bool:
	if not should_show_coreedge_controls():
		return True
	app = product_app or get_vetedge_product_app()
	try:
		from coreedge.adapters.access import has_product_access
		return has_product_access(product_app=app, tenant=tenant, user=user)
	except (ImportError, ModuleNotFoundError):
		return True

def require_vetedge_access(product_app: str | None = None, tenant: str | None = None, user: str | None = None) -> None:
	app = product_app or get_vetedge_product_app()
	
	is_enabled = is_coreedge_enabled()
	is_available = is_coreedge_available()
	
	if is_enabled and not is_available:
		if frappe.db.get_single_value("Veterinary Settings", "fail_closed_when_coreedge_missing"):
			frappe.throw(
				_("CoreEdge Platform is required but not installed or available."),
				exc=frappe.PermissionError,
				title=_("Platform Access Required")
			)
		return

	if not is_enabled:
		return

	try:
		from coreedge.adapters.access import require_product_access
		require_product_access(product_app=app, tenant=tenant, user=user)
	except (ImportError, ModuleNotFoundError):
		if frappe.db.get_single_value("Veterinary Settings", "fail_closed_when_coreedge_missing"):
			frappe.throw(
				_("CoreEdge Platform is required but not installed or available."),
				exc=frappe.PermissionError,
				title=_("Platform Access Required")
			)

def get_vetedge_access_context(product_app: str | None = None, tenant: str | None = None, user: str | None = None) -> dict:
	if not should_show_coreedge_controls():
		return {"allowed": True, "enforcement_action": "Allow", "primary_reason_code": "PLATFORM_DISABLED"}
	app = product_app or get_vetedge_product_app()
	try:
		from coreedge.adapters.access import get_access_context
		return get_access_context(product_app=app, tenant=tenant, user=user)
	except (ImportError, ModuleNotFoundError):
		return {"allowed": True, "enforcement_action": "Allow", "primary_reason_code": "PLATFORM_MISSING"}

def get_visible_vetedge_sidebar_items(items: list[dict]) -> list[dict]:
	if should_show_coreedge_controls():
		return items
	filtered = []
	for item in items:
		label = item.get("label")
		link_to = item.get("link_to")
		is_coreedge = False
		if link_to and (link_to.startswith("CoreEdge") or link_to.startswith("coreedge")):
			is_coreedge = True
		elif label in ["Platform Settings", "Product Activation", "Onboarding", "Product Access", "Branch Context", "Company Context", "CoreEdge Platform"]:
			is_coreedge = True
		if not is_coreedge:
			filtered.append(item)
	return filtered

def get_visible_vetedge_settings_items(items: list[dict]) -> list[dict]:
	if should_show_coreedge_controls():
		return items
	filtered = []
	for item in items:
		name = item.get("name") or item.get("label") or ""
		if not (name.startswith("CoreEdge") or name.startswith("coreedge") or name in ["Platform Settings", "Product Activation", "Onboarding", "Product Access", "Branch Context", "Company Context", "CoreEdge Platform"]):
			filtered.append(item)
	return filtered

def filter_bootinfo_for_coreedge_platform(bootinfo):
	bootinfo.is_coreedge_available = is_coreedge_available()
	bootinfo.should_show_coreedge_controls = should_show_coreedge_controls()
	
	if not bootinfo.should_show_coreedge_controls:
		sidebar_items = bootinfo.get("workspace_sidebar_item")
		if sidebar_items and "vetedge" in sidebar_items:
			items = sidebar_items["vetedge"].get("items") or []
			sidebar_items["vetedge"]["items"] = get_visible_vetedge_sidebar_items(items)
		
		workspaces_data = bootinfo.get("workspaces")
		if workspaces_data and "pages" in workspaces_data:
			filtered_pages = []
			for p in workspaces_data["pages"]:
				title = p.get("title") or p.get("name") or ""
				if not (title.startswith("CoreEdge") or title.startswith("coreedge") or title in ["Platform Settings", "Product Activation", "Onboarding", "Product Access", "Branch Context", "Company Context"]):
					filtered_pages.append(p)
			workspaces_data["pages"] = filtered_pages
