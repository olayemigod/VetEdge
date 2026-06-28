from __future__ import annotations

import frappe

from vetedge.install.custom_fields import ensure_custom_fields
from vetedge.install.dashboard import ensure_financial_dashboard
from vetedge.install.print_formats import ensure_print_formats
from vetedge.seed.master_data import seed_master_data
from vetedge.setup.email_templates import sync_vetedge_email_templates
from vetedge.services.feature_flags import DEFAULT_FEATURE_FLAGS, SETTINGS_DOCTYPE
from vetedge.services.portal_access import normalize_owner_portal_users
from vetedge.services.role_bundles import (
	ensure_existing_internal_users_have_starter_bundle_roles,
	ensure_starter_role_bundles,
)


def after_install() -> None:
	setup_foundation()


def after_migrate() -> None:
	setup_foundation()


def before_tests() -> None:
	ensure_erpnext_test_price_lists_are_idempotent()


def setup_foundation() -> None:
	ensure_vetedge_roles()
	ensure_starter_role_bundles()
	ensure_existing_internal_users_have_starter_bundle_roles()
	ensure_custom_fields()
	ensure_veterinary_settings()
	cleanup_stale_portal_menu_items()
	normalize_owner_portal_users()
	ensure_print_formats()
	seed_master_data()
	sync_vetedge_email_templates()
	ensure_financial_dashboard()


def ensure_vetedge_roles() -> None:
	for role, desk_access in (
		("VetEdge Administrator", 1),
		("VetEdge Front Desk", 1),
		("VetEdge Doctor", 1),
		("VetEdge Groomer", 1),
		("Veterinary Nurse", 1),
		("VetEdge Nurse", 1),
		("Dispensary User", 1),
		("Lab Technician", 1),
		("Branch Manager", 1),
		("VetEdge Branch Manager", 1),
		("Accounts/Cashier", 1),
		("VetEdge Portal User", 0),
	):
		if frappe.db.exists("Role", role):
			continue

		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role,
				"desk_access": desk_access,
			}
		).insert(ignore_permissions=True)


def ensure_erpnext_test_price_lists_are_idempotent() -> None:
	"""Align existing standard Price Lists with ERPNext's test bootstrap filters.

	ERPNext test dependencies import doctype tests that run BootStrapTestData.
	That bootstrap checks Standard Buying/Selling with a filter that includes
	currency and flags before inserting, while Price List name is still the
	primary key. Existing local test sites commonly have these rows in the site
	currency, so the filter misses them and the insert fails with a duplicate key.
	"""
	if not getattr(frappe, "in_test", False) or not frappe.db.exists("DocType", "Price List"):
		return

	for price_list_name, buying, selling in (
		("Standard Buying", 1, 0),
		("Standard Selling", 0, 1),
	):
		if not frappe.db.exists("Price List", price_list_name):
			continue

		frappe.db.set_value(
			"Price List",
			price_list_name,
			{
				"enabled": 1,
				"buying": buying,
				"selling": selling,
				"currency": "INR",
			},
			update_modified=False,
		)


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
	titles = {"VetEdge Owner Portal", "Owner Portal", "Book Veterinary Appointment"}
	changed = False

	for table_field in ("menu", "custom_menu"):
		for item in list(portal_settings.get(table_field) or []):
			if item.route in routes or item.title in titles:
				portal_settings.remove(item)
				changed = True

	if changed:
		portal_settings.save(ignore_permissions=True)
