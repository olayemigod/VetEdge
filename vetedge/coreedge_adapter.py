# -*- coding: utf-8 -*-
from __future__ import annotations

import frappe
from frappe import _

def is_coreedge_available() -> bool:
	try:
		return "coreedge" in frappe.get_installed_apps()
	except Exception:
		return False

def _parse_config_bool(val) -> bool:
	if val is None:
		return False
	if isinstance(val, bool):
		return val
	if isinstance(val, int):
		return val != 0
	val_str = str(val).strip().lower()
	if val_str in ("1", "true", "yes", "on"):
		return True
	return False

def get_edge_platform_mode() -> str:
	try:
		mode = frappe.conf.get("edge_platform_mode")
		if mode is not None:
			mode = str(mode).strip()
		if not mode:
			return "standalone"
		
		supported_modes = {"standalone", "shared_hosted", "white_label"}
		if mode not in supported_modes:
			try:
				frappe.logger().error(
					f"Invalid edge_platform_mode '{mode}' configured in site_config. "
					"Failing safe to required mode behavior."
				)
			except Exception:
				pass
		return mode
	except Exception:
		return "standalone"

def is_coreedge_enabled() -> bool:
	try:
		required = _parse_config_bool(frappe.conf.get("coreedge_required"))
		if required:
			return True
		
		mode = get_edge_platform_mode()
		if mode in ("shared_hosted", "white_label"):
			return True
		elif mode == "standalone":
			return False
		else:
			return True
	except Exception:
		return False

def should_fail_closed_when_coreedge_missing() -> bool:
	return is_coreedge_enabled()

def should_show_coreedge_controls() -> bool:
	return is_coreedge_available() and is_coreedge_enabled()

def get_vetedge_product_app() -> str:
	try:
		val = frappe.conf.get("edge_platform_product")
		if val is not None:
			val = str(val).strip()
		return val or "VetEdge"
	except Exception:
		return "VetEdge"

def get_vetedge_desk_route() -> str:
	return "/desk/vetedge-executive-dashboard"

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
		try:
			return has_product_access(product_code=app, tenant=tenant, user=user)
		except TypeError:
			return has_product_access(product_app=app, tenant=tenant, user=user)
	except (ImportError, ModuleNotFoundError):
		return True

def require_vetedge_access(
	product_app: str | None = None,
	tenant: str | None = None,
	user: str | None = None,
	action: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> None:
	app = product_app or get_vetedge_product_app()
	
	is_enabled = is_coreedge_enabled()
	is_available = is_coreedge_available()
	fail_closed = should_fail_closed_when_coreedge_missing()
	
	if is_enabled and not is_available:
		if fail_closed:
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
		try:
			require_product_access(
				product_code=app,
				tenant=tenant,
				user=user,
				source_app=action,
				source_doctype=reference_doctype,
				source_docname=reference_name
			)
		except TypeError:
			try:
				require_product_access(
					product_app=app,
					tenant=tenant,
					user=user,
					source_app=action,
					source_doctype=reference_doctype,
					source_docname=reference_name
				)
			except TypeError:
				try:
					require_product_access(product_code=app, tenant=tenant, user=user)
				except TypeError:
					require_product_access(product_app=app, tenant=tenant, user=user)
	except (ImportError, ModuleNotFoundError):
		if fail_closed:
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
		try:
			return get_access_context(product_code=app, tenant=tenant, user=user)
		except TypeError:
			try:
				return get_access_context(product_app=app, tenant=tenant, user=user)
			except TypeError:
				return get_access_context(user=user)
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

def _get_allowed_workspace_names(bootinfo) -> list[str]:
	try:
		pages = (bootinfo.get("workspaces") or {}).get("pages") or []
	except Exception:
		return []
	return [page.get("name") for page in pages if page.get("name")]

def _build_sidebar_item_for_boot(item) -> dict:
	boot_item = {
		"label": item.label,
		"link_to": item.link_to,
		"link_type": item.link_type,
		"type": item.type,
		"icon": item.icon,
		"child": item.child,
		"collapsible": item.collapsible,
		"indent": item.indent,
		"keep_closed": item.keep_closed,
		"url": item.url,
		"show_arrow": item.show_arrow,
		"filters": item.filters,
		"route_options": item.route_options,
		"tab": item.navigate_to_tab,
	}
	if (
		item.link_type == "Report"
		and item.link_to
		and frappe.db.exists("Report", item.link_to)
		and not frappe.db.get_value("Report", item.link_to, "disabled")
	):
		report_type, ref_doctype = frappe.db.get_value(
			"Report", item.link_to, ["report_type", "ref_doctype"]
		)
		boot_item["report"] = {"report_type": report_type, "ref_doctype": ref_doctype}
	return boot_item

def get_canonical_vetedge_sidebar_for_boot(bootinfo) -> dict | None:
	if not frappe.db.exists("DocType", "Workspace Sidebar") or not frappe.db.exists("Workspace Sidebar", "VetEdge"):
		return None

	sidebar_doc = frappe.get_doc("Workspace Sidebar", "VetEdge")
	allowed_workspaces = _get_allowed_workspace_names(bootinfo)
	items = []
	for item in sidebar_doc.items:
		if (
			item.type == "Section Break"
			or sidebar_doc.is_item_allowed(item.link_to, item.link_type, allowed_workspaces)
		):
			items.append(_build_sidebar_item_for_boot(item))

	if not any(item["type"] != "Section Break" for item in items):
		return None

	return {
		"label": "Veterinary",
		"items": items,
		"header_icon": sidebar_doc.header_icon,
		"module_onboarding": sidebar_doc.module_onboarding,
		"module": sidebar_doc.module,
		"app": sidebar_doc.app,
	}

def filter_bootinfo_for_coreedge_platform(bootinfo):
	bootinfo.is_coreedge_available = is_coreedge_available()
	bootinfo.should_show_coreedge_controls = should_show_coreedge_controls()
	
	try:
		from vetedge.services.branding import get_branding
		branding = get_branding()
	except Exception:
		branding = {}

	# Always map the sidebar under both "vetedge" and "veterinary" to ensure both route and desktop icon resolve correctly
	sidebar_items = bootinfo.get("workspace_sidebar_item")
	if sidebar_items:
		source_sidebar = get_canonical_vetedge_sidebar_for_boot(bootinfo)
		if source_sidebar:
			source_sidebar["label"] = branding.get("module_label") or "Veterinary"
			sidebar_items["veterinary"] = source_sidebar
			sidebar_items["vetedge"] = source_sidebar

	# Always override the desktop icon label in bootinfo to be VetEdge (or the branded app_title)
	desktop_icons = bootinfo.get("desktop_icons")
	if desktop_icons:
		for icon in desktop_icons:
			if icon.get("app") == "vetedge" and icon.get("name") in ("VetEdge", "Veterinary"):
				icon["label"] = branding.get("app_title") or branding.get("brand_name") or "VetEdge"
				icon["link_type"] = "External"
				icon["link"] = get_vetedge_desk_route()
				icon["link_to"] = "VetEdge"

	# Always override the app_data app_title and logo for app screen
	if bootinfo.get("app_data"):
		for app in bootinfo.app_data:
			if app.get("app_name") == "vetedge":
				app["app_title"] = branding.get("app_title") or branding.get("brand_name") or "VetEdge"
				app["route"] = get_vetedge_desk_route()
				if branding.get("logo"):
					app["app_logo_url"] = branding.get("logo")

	# Apply white-label overrides if enabled
	if branding.get("enabled"):
		# Set app title in bootinfo for the tab title suffix
		bootinfo.app_title = branding.get("app_title") or branding.get("brand_name") or "VetEdge"
		
		# Override app logo url dynamically
		if branding.get("logo"):
			bootinfo.app_logo_url = branding.get("logo")
			if bootinfo.get("navbar_settings"):
				bootinfo.navbar_settings.app_logo = branding.get("logo")
			
			# Patch frappe.boot's get_app_logo reference to return the branded logo url
			try:
				import frappe.boot as boot
				boot.get_app_logo = lambda: branding.get("logo")
			except Exception:
				pass

	if not bootinfo.should_show_coreedge_controls:
		if sidebar_items and "vetedge" in sidebar_items:
			items = sidebar_items["vetedge"].get("items") or []
			sidebar_items["vetedge"]["items"] = get_visible_vetedge_sidebar_items(items)
		if sidebar_items and "veterinary" in sidebar_items:
			items = sidebar_items["veterinary"].get("items") or []
			sidebar_items["veterinary"]["items"] = get_visible_vetedge_sidebar_items(items)
		
		workspaces_data = bootinfo.get("workspaces")
		if workspaces_data and "pages" in workspaces_data:
			filtered_pages = []
			for p in workspaces_data["pages"]:
				title = p.get("title") or p.get("name") or ""
				if not (title.startswith("CoreEdge") or title.startswith("coreedge") or title in ["Platform Settings", "Product Activation", "Onboarding", "Product Access", "Branch Context", "Company Context"]):
					filtered_pages.append(p)
			workspaces_data["pages"] = filtered_pages
