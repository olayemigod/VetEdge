from __future__ import annotations

import frappe


REMOVED_WORKSPACES = ("Veterinary Hospitalisation Dashboard", "VetEdge Hospitalisation Dashboard")


def execute():
	_remove_sidebar_shortcut()
	for workspace in REMOVED_WORKSPACES:
		frappe.delete_doc_if_exists("Workspace", workspace, force=1)
	_clear_dashboard_cache()


def _remove_sidebar_shortcut():
	if not frappe.db.exists("DocType", "Workspace Sidebar"):
		return
	if not frappe.db.exists("Workspace Sidebar", "VetEdge"):
		return

	sidebar = frappe.get_doc("Workspace Sidebar", "VetEdge")
	items = [
		item
		for item in sidebar.get("items")
		if not (
			item.get("link_type") == "Workspace"
			and item.get("link_to") in REMOVED_WORKSPACES
		)
	]
	if len(items) == len(sidebar.get("items")):
		return

	sidebar.set("items", items)
	sidebar.save(ignore_permissions=True)


def _clear_dashboard_cache():
	if hasattr(frappe, "cache"):
		frappe.cache.delete_key("bootinfo")
		frappe.cache.delete_key("desktop_icons")
