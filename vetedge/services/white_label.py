from __future__ import annotations

import frappe


DEFAULT_LABEL = "Veterinary"
DEFAULT_HEADER_ICON = "octicon octicon-heart"
DEFAULT_APP_ICON = "/assets/vetedge/images/vetedge-app-icon.png"


def get_white_label_context() -> dict:
	"""Resolve tenant/app-shell branding.

	Priority:
	1. CoreEdge branding resolver later, if available.
	2. site_config values.
	3. generic Veterinary fallback.
	"""
	coreedge_context = _get_coreedge_branding_context()
	site_config_context = _get_site_config_branding_context()

	app_label = (
		coreedge_context.get("app_label")
		or site_config_context.get("app_label")
		or DEFAULT_LABEL
	)

	app_short_label = (
		coreedge_context.get("app_short_label")
		or site_config_context.get("app_short_label")
		or app_label
		or DEFAULT_LABEL
	)

	launcher_label = (
		coreedge_context.get("launcher_label")
		or site_config_context.get("launcher_label")
		or app_short_label
		or DEFAULT_LABEL
	)

	workspace_label = (
		coreedge_context.get("workspace_label")
		or site_config_context.get("workspace_label")
		or launcher_label
		or DEFAULT_LABEL
	)

	module_label = (
		coreedge_context.get("module_label")
		or site_config_context.get("module_label")
		or workspace_label
		or DEFAULT_LABEL
	)

	workspace_header_icon = (
		coreedge_context.get("workspace_header_icon")
		or site_config_context.get("workspace_header_icon")
		or DEFAULT_HEADER_ICON
	)

	app_icon = (
		coreedge_context.get("app_icon")
		or site_config_context.get("app_icon")
		or DEFAULT_APP_ICON
	)

	launcher_icon = (
		coreedge_context.get("launcher_icon")
		or site_config_context.get("launcher_icon")
		or app_icon
		or DEFAULT_APP_ICON
	)

	return {
		"app_label": app_label,
		"app_short_label": app_short_label,
		"launcher_label": launcher_label,
		"workspace_label": workspace_label,
		"module_label": module_label,
		"workspace_header_icon": workspace_header_icon,
		"app_icon": app_icon,
		"launcher_icon": launcher_icon,
	}


def _get_site_config_branding_context() -> dict:
	return {
		"app_label": _conf("vetedge_app_label"),
		"app_short_label": _conf("vetedge_app_short_label"),
		"launcher_label": _conf("vetedge_launcher_label"),
		"workspace_label": _conf("vetedge_workspace_sidebar_label"),
		"module_label": _conf("vetedge_module_label"),
		"workspace_header_icon": _conf("vetedge_workspace_header_icon"),
		"app_icon": _conf("vetedge_app_icon"),
		"launcher_icon": _conf("vetedge_launcher_icon"),
	}


def _get_coreedge_branding_context() -> dict:
	"""Safe future bridge to CoreEdge branding.

	This must never break VetEdge migration when CoreEdge is missing.
	"""
	try:
		if "coreedge" not in frappe.get_installed_apps():
			return {}

		# Future integration point:
		# call get_active_branding_context from the core platform app
		# return get_active_branding_context(product="vetedge") or {}

		return {}
	except Exception:
		return {}


def _conf(key: str) -> str | None:
	value = frappe.conf.get(key)
	if value is None:
		return None

	value = str(value).strip()
	return value or None
