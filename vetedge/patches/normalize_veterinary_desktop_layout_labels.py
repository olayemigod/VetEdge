from __future__ import annotations

import json

import frappe


OLD_LABEL = "VetEdge"
NEW_LABEL = "Veterinary"
APP_NAME = "vetedge"


def _normalize_layout_node(value):
	"""Normalize VetEdge desktop-layout snapshots without changing user arrangement."""
	changed = False

	if isinstance(value, list):
		for item in value:
			if _normalize_layout_node(item):
				changed = True
		return changed

	if not isinstance(value, dict):
		return False

	is_vetedge_icon = value.get("app") == APP_NAME
	if is_vetedge_icon and value.get("icon_type") == "App" and value.get("label") == OLD_LABEL:
		value["label"] = NEW_LABEL
		changed = True

	# Desktop Layout is a JSON snapshot, not Link-field storage. Frappe's icon-grid renderer
	# resolves parent_icon against the parent's visible label, so saved VetEdge children must
	# follow the visible label even though the canonical Desktop Icon document name stays VetEdge.
	if is_vetedge_icon and value.get("parent_icon") == OLD_LABEL:
		value["parent_icon"] = NEW_LABEL
		changed = True

	for nested in value.values():
		if isinstance(nested, (dict, list)) and _normalize_layout_node(nested):
			changed = True

	return changed


def _normalize_canonical_icon() -> None:
	if not frappe.db.exists("DocType", "Desktop Icon"):
		return
	if not frappe.db.exists("Desktop Icon", OLD_LABEL):
		return
	if frappe.db.get_value("Desktop Icon", OLD_LABEL, "label") == NEW_LABEL:
		return

	frappe.db.set_value(
		"Desktop Icon",
		OLD_LABEL,
		"label",
		NEW_LABEL,
		update_modified=False,
	)


def _normalize_saved_layouts() -> None:
	if not frappe.db.exists("DocType", "Desktop Layout"):
		return

	for row in frappe.get_all("Desktop Layout", fields=["name", "layout"]):
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
	"""Repair stale per-user Desktop Layout snapshots after the visible Veterinary rename."""
	_normalize_canonical_icon()
	_normalize_saved_layouts()

	# Desktop icons and bootinfo are cached per user. Clear the whole cache keys because the
	# patch may have updated layouts belonging to multiple users.
	frappe.cache.delete_key("desktop_icons")
	frappe.cache.delete_key("bootinfo")
