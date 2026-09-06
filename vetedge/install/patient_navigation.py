from __future__ import annotations

from typing import Any

import frappe

PATIENT_LABEL = "Patients"
PATIENT_DOCTYPE = "Veterinary Patient"
SIDEBAR_NAME = "VetEdge"
CHILD_META_FIELDS = {
	"name",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"docstatus",
	"idx",
	"parent",
	"parentfield",
	"parenttype",
	"doctype",
}


def _clean_item(item: Any) -> dict:
	if isinstance(item, dict):
		data = dict(item)
	elif hasattr(item, "as_dict"):
		data = dict(item.as_dict())
	else:
		data = {
			field: getattr(item, field)
			for field in (
				"child",
				"collapsible",
				"display_depends_on",
				"icon",
				"indent",
				"keep_closed",
				"label",
				"link_to",
				"link_type",
				"show_arrow",
				"type",
				"url",
			)
			if hasattr(item, field)
		}
	return {key: value for key, value in data.items() if key not in CHILD_META_FIELDS}


def _is_section(item: dict) -> bool:
	return item.get("type") == "Section Break" and not int(item.get("child") or 0)


def _is_patient_link(item: dict) -> bool:
	if item.get("type") != "Link":
		return False
	label = str(item.get("label") or "").strip()
	link_to = str(item.get("link_to") or "").strip()
	return label == PATIENT_LABEL or link_to == PATIENT_DOCTYPE


def _dedicated_patient_section_ranges(items: list[dict]) -> set[int]:
	"""Return indexes for canonical/legacy one-item Patients sections only.

	A customized Patients section containing any other link is left intact. This
	prevents the navigation cleanup from deleting administrator-added content.
	"""
	remove: set[int] = set()
	index = 0
	while index < len(items):
		item = items[index]
		if not (_is_section(item) and str(item.get("label") or "").strip() == PATIENT_LABEL):
			index += 1
			continue

		end = index + 1
		while end < len(items) and not _is_section(items[end]):
			end += 1
		children = items[index + 1 : end]
		meaningful = [child for child in children if child.get("type") == "Link"]
		if meaningful and all(_is_patient_link(child) for child in meaningful):
			remove.update(range(index, end))
		index = end
	return remove


def _patient_group(template: dict) -> list[dict]:
	visibility = template.get("display_depends_on")
	section = {
		"child": 0,
		"collapsible": 1,
		"icon": "users-round",
		"indent": 1,
		"keep_closed": 0,
		"label": PATIENT_LABEL,
		"link_type": "DocType",
		"show_arrow": 0,
		"type": "Section Break",
	}
	if visibility:
		section["display_depends_on"] = visibility

	link = dict(template)
	link.update(
		{
			"child": 1,
			"collapsible": 0,
			"icon": "users-round",
			"indent": 0,
			"keep_closed": 0,
			"label": PATIENT_LABEL,
			"link_to": PATIENT_DOCTYPE,
			"link_type": "DocType",
			"show_arrow": 0,
			"type": "Link",
		}
	)
	link.pop("url", None)
	return [section, link]


def organize_direct_patient_navigation(items: list[Any]) -> list[dict]:
	"""Move Patients out of Front Desk into its own first-class navigation group.

	The returned structure is idempotent. Existing Patients visibility is copied
	from the source link so this layout change never broadens role access.
	"""
	clean = [_clean_item(item) for item in items]
	template = next((dict(item) for item in clean if _is_patient_link(item)), None)
	if not template:
		return clean

	remove_indexes = _dedicated_patient_section_ranges(clean)
	remaining = [
		item
		for index, item in enumerate(clean)
		if index not in remove_indexes and not _is_patient_link(item)
	]

	# Veterinary Home is a direct child=0 Link prepended by dashboard sync. Keep
	# all leading direct links in place, then insert Patients before Dashboard.
	insert_at = 0
	while insert_at < len(remaining):
		item = remaining[insert_at]
		if item.get("type") == "Link" and not int(item.get("child") or 0):
			insert_at += 1
			continue
		break

	return [*remaining[:insert_at], *_patient_group(template), *remaining[insert_at:]]


def ensure_direct_patient_navigation() -> bool:
	"""Apply the direct Patients contract after normal VetEdge sidebar sync."""
	if not frappe.db.exists("DocType", "Workspace Sidebar") or not frappe.db.exists(
		"Workspace Sidebar", SIDEBAR_NAME
	):
		return False

	sidebar = frappe.get_doc("Workspace Sidebar", SIDEBAR_NAME)
	current = [_clean_item(item) for item in (sidebar.get("items") or [])]
	updated = organize_direct_patient_navigation(current)
	if updated == current:
		return False

	sidebar.set("items", updated)
	sidebar.save(ignore_permissions=True)
	if hasattr(frappe, "cache"):
		frappe.cache.delete_key("bootinfo")
	return True
