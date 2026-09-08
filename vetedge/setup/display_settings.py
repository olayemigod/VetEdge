from __future__ import annotations

import frappe

VETEDGE_DATE_FORMAT = "dd-mm-yyyy"


def ensure_vetedge_date_format() -> bool:
	"""Set the site display format used by native Frappe Date controls.

	This changes presentation only. Frappe continues to store and transport dates
	in its normal database/ISO formats.
	"""
	if not frappe.db.exists("DocType", "System Settings"):
		return False

	settings = frappe.get_single("System Settings")
	if settings.get("date_format") == VETEDGE_DATE_FORMAT:
		return False

	settings.date_format = VETEDGE_DATE_FORMAT
	settings.save(ignore_permissions=True)
	frappe.clear_cache()
	return True
