from __future__ import annotations

import json

import frappe


OLD_LABEL = "VetEdge"
NEW_LABEL = "Veterinary"
APP_NAME = "vetedge"


def _normalize_layout_node(value):
	"""Normalize the visible VetEdge root tile in saved Desktop Layout snapshots."""
	changed = False

	if isinstance(value, list):
		for item in value:
			if _normalize_layout_node(item):
				changed = True
		return changed

	if not isinstance(value, dict):
		return False

	is_vetedge_row = value.get("app") == APP_NAME
	is_vetedge_root = is_vetedge_row and (
		value.get("name") == OLD_LABEL or value.get("link_to") == OLD_LABEL
	)

	# In Frappe v16 Desktop Icons mode the VetEdge root tile is a Link to the
	# VetEdge Workspace Sidebar, not an App icon. Keep the stored document/link
	# identity stable and change only the user-facing label.
	if is_vetedge_root and value.get("label") == OLD_LABEL:
		value["label"] = NEW_LABEL
		changed = True

	# Child snapshots resolve parent_icon against the visible parent label.
	if is_vetedge_row and value.get("parent_icon") == OLD_LABEL:
		value["parent_icon"] = NEW_LABEL
		changed = True

	for nested in value.values():
		if isinstance(nested, (dict, list)) and _normalize_layout_node(nested):
			changed = True

	return changed


def execute() -> None:
	"""Repair Frappe v16 saved Desktop Layouts that still render VetEdge."""
	if not frappe.db.exists("DocType", "Desktop Layout"):
		return

	affected_users: set[str] = set()

	for row in frappe.get_all("Desktop Layout", fields=["name", "user", "layout"]):
		if not row.layout:
			continue

		try:
			layout = json.loads(row.layout) if isinstance(row.layout, str) else row.layout
		except (TypeError, ValueError):
			continue

		if not _normalize_layout_node(layout):
			continue

		frappe.db.set_value(
			"Desktop Layout",
			row.name,
			"layout",
			json.dumps(layout),
			update_modified=False,
		)
		affected_users.add(row.user or row.name)

	# Match Frappe's own cache invalidation for Desktop Icons. This avoids
	# resetting layouts while forcing a fresh boot payload for affected users.
	if affected_users:
		from frappe.desk.doctype.desktop_icon.desktop_icon import clear_desktop_icons_cache

		for user in affected_users:
			clear_desktop_icons_cache(user=user)
