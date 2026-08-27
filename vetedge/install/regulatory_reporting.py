from __future__ import annotations

import os

import frappe
from frappe.modules.import_file import import_file_by_path


REGULATORY_PAGE = "vetedge-regulatory-reporting"
OUTBREAK_DOCTYPE = "Veterinary Disease Outbreak"
ADMINISTRATION_PAGE = "vetedge-administration"
SIDEBAR_NAME = "VetEdge"
SECTION_LABEL = "Regulatory Reporting"
CONFIGURATION_SECTION_LABEL = "Configuration"
ADMINISTRATION_SECTION_LABEL = "Administration"

LEGACY_ADMINISTRATION_LINKS = {
	("DocType", "Veterinary Notification Preference"),
	("DocType", "Veterinary Notification Log"),
	("DocType", "Veterinary Role Bundle"),
	("DocType", "Veterinary License Profile"),
	("DocType", "Veterinary Notification Item"),
}
CONFIGURATION_LINK_ORDER = (
	("DocType", "Veterinary Settings"),
	("DocType", "Branch"),
	("DocType", "Veterinary Care Location"),
	("DocType", "Kennel"),
	("DocType", "Cost Center"),
	("DocType", "Branch User Assignment"),
	("DocType", "Branch Practitioner Assignment"),
)
CONFIGURATION_LINKS = set(CONFIGURATION_LINK_ORDER)
CHILD_METADATA_FIELDS = {
	"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx",
	"doctype", "parent", "parentfield", "parenttype",
}

REGULATORY_VISIBILITY = (
	"eval: frappe.user.has_role('System Manager') || frappe.user.has_role('VetEdge Administrator') || "
	"frappe.user.has_role('VetEdge Doctor') || frappe.user.has_role('Veterinary Nurse') || "
	"frappe.user.has_role('Branch Manager')"
)
ADMINISTRATION_VISIBILITY = (
	"eval: frappe.user.has_role('System Manager') || frappe.user.has_role('VetEdge Administrator')"
)


def _section(label):
	return {
		"type": "Section Break", "label": label, "link_type": "DocType", "child": 0,
		"collapsible": 1, "indent": 1, "keep_closed": 1, "show_arrow": 0,
	}


def _link(label, link_type, link_to, icon, visibility):
	return {
		"type": "Link", "label": label, "link_type": link_type, "link_to": link_to,
		"icon": icon, "child": 1, "collapsible": 0, "indent": 0, "keep_closed": 0,
		"show_arrow": 0, "display_depends_on": visibility,
	}


def _row_payload(item):
	if hasattr(item, "as_dict"):
		item = item.as_dict()
	return {key: value for key, value in dict(item or {}).items() if key not in CHILD_METADATA_FIELDS}


def _is_section(item, label):
	return item.get("type") == "Section Break" and item.get("label") == label


def _signature(item):
	return item.get("link_type"), item.get("link_to")


def _next_section(items, start):
	for index in range(start + 1, len(items)):
		if items[index].get("type") == "Section Break":
			return index
	return len(items)


def _normalise_sidebar_items(items, *, include_outbreak=True, include_administration=True):
	"""Rebuild managed sidebar groups without persisted child-row metadata."""
	cleaned = [_row_payload(item) for item in items]

	config_start = next(
		(index for index, item in enumerate(cleaned) if _is_section(item, CONFIGURATION_SECTION_LABEL)),
		-1,
	)
	config_end = _next_section(cleaned, config_start) if config_start >= 0 else -1
	config_segment = cleaned[config_start + 1:config_end] if config_start >= 0 else []

	config_rows = {}
	for item in cleaned:
		signature = _signature(item)
		if item.get("type") == "Link" and signature in CONFIGURATION_LINKS and signature not in config_rows:
			config_rows[signature] = item

	config_extras = []
	seen_extras = set()
	for item in config_segment:
		signature = _signature(item)
		if item.get("type") != "Link" or signature in CONFIGURATION_LINKS:
			continue
		if signature in {("Page", REGULATORY_PAGE), ("DocType", OUTBREAK_DOCTYPE)}:
			continue
		if include_administration and (signature == ("Page", ADMINISTRATION_PAGE) or signature in LEGACY_ADMINISTRATION_LINKS):
			continue
		if signature not in seen_extras:
			config_extras.append(item)
			seen_extras.add(signature)

	filtered = []
	for index, item in enumerate(cleaned):
		signature = _signature(item)
		if config_start >= 0 and config_start <= index < config_end:
			continue
		if _is_section(item, CONFIGURATION_SECTION_LABEL) or (item.get("type") == "Link" and signature in CONFIGURATION_LINKS):
			continue
		if _is_section(item, SECTION_LABEL) or signature in {("Page", REGULATORY_PAGE), ("DocType", OUTBREAK_DOCTYPE)}:
			continue
		if include_administration and (
			_is_section(item, ADMINISTRATION_SECTION_LABEL)
			or signature == ("Page", ADMINISTRATION_PAGE)
			or signature in LEGACY_ADMINISTRATION_LINKS
		):
			continue
		filtered.append(item)

	managed = [
		_section(SECTION_LABEL),
		_link("VCN / NADIS Reports", "Page", REGULATORY_PAGE, "shield-check", REGULATORY_VISIBILITY),
	]
	if include_outbreak:
		managed.append(_link("Disease Outbreak Register", "DocType", OUTBREAK_DOCTYPE, "alert-triangle", REGULATORY_VISIBILITY))

	managed.append(_section(CONFIGURATION_SECTION_LABEL))
	managed.extend(config_rows[signature] for signature in CONFIGURATION_LINK_ORDER if signature in config_rows)
	managed.extend(config_extras)

	if include_administration:
		managed.extend([
			_section(ADMINISTRATION_SECTION_LABEL),
			_link("Administration", "Page", ADMINISTRATION_PAGE, "user-cog", ADMINISTRATION_VISIBILITY),
		])

	insert_at = next(
		(index for index, item in enumerate(filtered) if item.get("type") == "Section Break" and item.get("label") in {"Platform", "Help & Training"}),
		len(filtered),
	)
	filtered[insert_at:insert_at] = managed
	return filtered


def ensure_regulatory_reporting_navigation() -> None:
	"""Repair VetEdge regulatory, configuration and administration navigation."""
	if not frappe.db.exists("DocType", "Page"):
		return
	if not frappe.db.exists("Page", REGULATORY_PAGE):
		page_file = frappe.get_app_path(
			"vetedge", "veterinary", "page", "vetedge_regulatory_reporting", "vetedge_regulatory_reporting.json"
		)
		if os.path.exists(page_file):
			import_file_by_path(page_file, force=True, ignore_version=True)
	if not frappe.db.exists("Page", REGULATORY_PAGE):
		return
	if not frappe.db.exists("DocType", "Workspace Sidebar") or not frappe.db.exists("Workspace Sidebar", SIDEBAR_NAME):
		return

	sidebar = frappe.get_doc("Workspace Sidebar", SIDEBAR_NAME)
	current = [_row_payload(item) for item in list(sidebar.get("items") or [])]
	normalised = _normalise_sidebar_items(
		list(sidebar.get("items") or []),
		include_outbreak=bool(frappe.db.exists("DocType", OUTBREAK_DOCTYPE)),
		include_administration=bool(frappe.db.exists("Page", ADMINISTRATION_PAGE)),
	)
	if current == normalised:
		return

	sidebar.set("items", normalised)
	sidebar.save(ignore_permissions=True)
	frappe.cache.delete_key("bootinfo")
