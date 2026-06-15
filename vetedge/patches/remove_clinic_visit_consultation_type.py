from __future__ import annotations

import frappe


def execute() -> None:
	if not frappe.db.table_exists("Consultation Type"):
		return

	if frappe.db.exists("Consultation Type", "Clinic Visit"):
		frappe.delete_doc("Consultation Type", "Clinic Visit", ignore_permissions=True, force=True)
