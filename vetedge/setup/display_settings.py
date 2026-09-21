from __future__ import annotations

import frappe

VETEDGE_DATE_FORMAT = "dd-mm-yyyy"


def ensure_vetedge_date_format() -> bool:
	"""Set the site display format used by native Frappe Date controls.

	This changes presentation only. Frappe continues to store and transport dates
	in its normal database/ISO formats.

	Use a direct Single DocType field update rather than saving the full System
	Settings document. During fresh app installation Frappe may not yet have
	populated unrelated mandatory fields such as language and time_zone; a full
	document save would incorrectly make VetEdge installation depend on them.
	"""
	if not frappe.db.exists("DocType", "System Settings"):
		return False

	if frappe.db.get_single_value("System Settings", "date_format") == VETEDGE_DATE_FORMAT:
		return False

	frappe.db.set_single_value(
		"System Settings",
		"date_format",
		VETEDGE_DATE_FORMAT,
		update_modified=False,
	)
	frappe.clear_cache()
	return True
