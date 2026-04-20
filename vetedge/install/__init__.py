from __future__ import annotations

import frappe

from vetedge.install.custom_fields import ensure_custom_fields
from vetedge.install.dashboard import ensure_financial_dashboard
from vetedge.seed.master_data import seed_master_data
from vetedge.services.feature_flags import DEFAULT_FEATURE_FLAGS, SETTINGS_DOCTYPE


def after_install() -> None:
	setup_foundation()


def after_migrate() -> None:
	setup_foundation()


def setup_foundation() -> None:
	ensure_vetedge_roles()
	ensure_custom_fields()
	ensure_veterinary_settings()
	cleanup_stale_portal_menu_items()
	seed_master_data()
	ensure_financial_dashboard()


def ensure_vetedge_roles() -> None:
	for role in ("VetEdge Administrator", "VetEdge Front Desk", "VetEdge Doctor"):
		if frappe.db.exists("Role", role):
			continue

		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role,
				"desk_access": 1,
			}
		).insert(ignore_permissions=True)


def ensure_veterinary_settings() -> None:
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return

	settings = frappe.get_single(SETTINGS_DOCTYPE)
	meta = frappe.get_meta(SETTINGS_DOCTYPE)
	changed = False

	for fieldname, value in DEFAULT_FEATURE_FLAGS.items():
		if not meta.has_field(fieldname):
			continue

		if settings.get(fieldname) in (None, ""):
			settings.set(fieldname, value)
			changed = True

	if changed:
		settings.save(ignore_permissions=True)


def cleanup_stale_portal_menu_items() -> None:
	if not frappe.db.exists("DocType", "Portal Settings"):
		return

	portal_settings = frappe.get_doc("Portal Settings", "Portal Settings")
	routes = {"/vetedge_portal", "/vetedge_guest_booking"}
	titles = {"VetEdge Owner Portal", "Book Veterinary Appointment"}
	changed = False

	for table_field in ("menu", "custom_menu"):
		for item in list(portal_settings.get(table_field) or []):
			if item.route in routes or item.title in titles:
				portal_settings.remove(item)
				changed = True

	if changed:
		portal_settings.save(ignore_permissions=True)
