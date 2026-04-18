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
	ensure_custom_fields()
	ensure_veterinary_settings()
	seed_master_data()
	ensure_financial_dashboard()


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
