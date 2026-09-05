from __future__ import annotations

import json

import frappe


OLD_LABEL = "VetEdge"
NEW_LABEL = "Veterinary"
APP_NAME = "vetedge"


def _normalize_layout_node(value):
	"""Normalize only the visible VetEdge label in saved Desktop Layout snapshots."""
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

	if is_vetedge_root and value.get("label") == OLD_LABEL:
		value["label"] = NEW_LABEL
		changed = True

	if is_vetedge_row and value.get("parent_icon") == OLD_LABEL:
		value["parent_icon"] = NEW_LABEL
		changed = True

	for nested in value.values():
		if isinstance(nested, (dict, list)) and _normalize_layout_node(nested):
			changed = True

	return changed


def _normalize_standard_desktop_icon() -> None:
	if not frappe.db.exists("DocType", "Desktop Icon"):
		return

	icons = frappe.get_all(
		"Desktop Icon",
		filters={"app": APP_NAME, "standard": 1},
		fields=["name", "label", "link_to", "link_type", "icon_type"],
	)
	for icon in icons:
		if (
			icon.link_type != "Workspace Sidebar"
			or icon.icon_type != "Link"
			or icon.link_to != OLD_LABEL
			or icon.label == NEW_LABEL
		):
			continue
		frappe.db.set_value(
			"Desktop Icon",
			icon.name,
			"label",
			NEW_LABEL,
			update_modified=False,
		)


def _normalize_saved_layouts() -> None:
	if not frappe.db.exists("DocType", "Desktop Layout"):
		return

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


def execute() -> None:
	"""Repair Veterinary desktop labels and invalidate every user's stale Desk cache.

	Frappe caches standard Desktop Icons and complete bootinfo per user. Earlier
	migrations updated the shared icon and only invalidated users whose saved
	layout changed, leaving other users able to keep the old VetEdge label.
	"""
	_normalize_standard_desktop_icon()
	_normalize_saved_layouts()

	# Standard DesktopIcon.on_update clears the complete cache keys, not just the
	# current user's hash entry. Mirror that behavior so every user rebuilds both
	# desktop icons and bootinfo from the corrected shared record/layout.
	frappe.cache.delete_key("desktop_icons")
	frappe.cache.delete_key("bootinfo")
