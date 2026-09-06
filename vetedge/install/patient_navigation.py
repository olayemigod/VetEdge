from __future__ import annotations

import os
from typing import Any

import frappe
from frappe.modules.import_file import import_file_by_path

PATIENT_LABEL = "Patients"
PATIENT_DOCTYPE = "Veterinary Patient"
BILLING_CENTER_LABEL = "Billing Center"
BILLING_SESSION_LABEL = "Billing Session"
BILLING_SESSION_DOCTYPE = "Veterinary Billing Session"
BILLING_SESSIONS_PAGE = "vetedge-billing-sessions"
SIDEBAR_NAME = "VetEdge"
PRIMARY_GROUP_ORDER = (
	("Patients",),
	("Front Desk", "Appointments"),
	("Clinical", "Clinical Operations"),
	("Hospital & Services",),
	("Inventory / Pharmacy", "Inventory / Dispensary"),
	("Billing Center",),
	("Dashboard",),
	("Reports",),
)
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
	"""Return indexes for canonical/legacy one-item Patients sections only."""
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
		links = [child for child in children if child.get("type") == "Link"]
		if links and all(_is_patient_link(child) for child in links):
			remove.update(range(index, end))
		index = end
	return remove


def _custom_patient_section_indexes(items: list[dict]) -> set[int]:
	"""Protect customized Patients sections that include non-Patient links."""
	protected: set[int] = set()
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
		links = [child for child in children if child.get("type") == "Link"]
		if any(not _is_patient_link(child) for child in links):
			protected.update(range(index, end))
		index = end
	return protected


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
	from the source link so this layout change never broadens role access. A
	customized Patients section containing additional links is preserved unchanged.
	"""
	clean = [_clean_item(item) for item in items]
	custom_indexes = _custom_patient_section_indexes(clean)
	if custom_indexes:
		return clean

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
	# all leading direct links in place, then insert Patients before grouped menus.
	insert_at = 0
	while insert_at < len(remaining):
		item = remaining[insert_at]
		if item.get("type") == "Link" and not int(item.get("child") or 0):
			insert_at += 1
			continue
		break

	return [*remaining[:insert_at], *_patient_group(template), *remaining[insert_at:]]


def organize_billing_session_navigation(items: list[Any]) -> list[dict]:
	"""Route the VetEdge Billing Session menu to its EdgeSuite worklist Page."""
	clean = [_clean_item(item) for item in items]
	current_section = ""
	for item in clean:
		if _is_section(item):
			current_section = str(item.get("label") or "").strip()
			continue
		if current_section != BILLING_CENTER_LABEL or item.get("type") != "Link":
			continue
		label = str(item.get("label") or "").strip()
		link_to = str(item.get("link_to") or "").strip()
		if label != BILLING_SESSION_LABEL and link_to != BILLING_SESSION_DOCTYPE:
			continue
		item["label"] = BILLING_SESSION_LABEL
		item["link_type"] = "Page"
		item["link_to"] = BILLING_SESSIONS_PAGE
		item.pop("url", None)
	return clean


def organize_primary_navigation_order(items: list[Any]) -> list[dict]:
	"""Apply the approved top-level order while preserving all group contents.

	Only named primary groups are moved. Any unlisted groups remain after Reports
	in their existing relative order, so this is a pure navigation-order change.
	"""
	clean = [_clean_item(item) for item in items]
	leading: list[dict] = []
	blocks: list[list[dict]] = []
	current: list[dict] | None = None

	for item in clean:
		if _is_section(item):
			if current:
				blocks.append(current)
			current = [item]
			continue
		if current is None:
			leading.append(item)
		else:
			current.append(item)
	if current:
		blocks.append(current)

	ordered: list[list[dict]] = []
	used: set[int] = set()
	for aliases in PRIMARY_GROUP_ORDER:
		for index, block in enumerate(blocks):
			if index in used:
				continue
			label = str(block[0].get("label") or "").strip()
			if label not in aliases:
				continue
			ordered.append(block)
			used.add(index)
			break

	ordered.extend(block for index, block in enumerate(blocks) if index not in used)
	return [*leading, *(item for block in ordered for item in block)]


def _ensure_billing_sessions_page() -> None:
	"""Import the standard Billing Sessions Page before assigning sidebar links."""
	if frappe.db.exists("Page", BILLING_SESSIONS_PAGE):
		return
	file_path = frappe.get_app_path(
		"vetedge",
		"veterinary",
		"page",
		"vetedge_billing_sessions",
		"vetedge_billing_sessions.json",
	)
	if os.path.exists(file_path):
		import_file_by_path(file_path, force=True, ignore_version=True)


def ensure_direct_patient_navigation() -> bool:
	"""Apply direct Patients, Billing Sessions Page and approved top-level order."""
	if not frappe.db.exists("DocType", "Workspace Sidebar") or not frappe.db.exists(
		"Workspace Sidebar", SIDEBAR_NAME
	):
		return False

	_ensure_billing_sessions_page()
	sidebar = frappe.get_doc("Workspace Sidebar", SIDEBAR_NAME)
	current = [_clean_item(item) for item in (sidebar.get("items") or [])]
	updated = organize_direct_patient_navigation(current)
	updated = organize_billing_session_navigation(updated)
	updated = organize_primary_navigation_order(updated)
	if updated == current:
		return False

	sidebar.set("items", updated)
	sidebar.save(ignore_permissions=True)
	if hasattr(frappe, "cache"):
		frappe.cache.delete_key("bootinfo")
	return True
