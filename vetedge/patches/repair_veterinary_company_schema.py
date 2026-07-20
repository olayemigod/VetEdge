from __future__ import annotations

import frappe


def execute():
	frappe.reload_doc("veterinary", "doctype", "veterinary_patient", force=True)
	frappe.reload_doc("veterinary", "doctype", "veterinary_appointment", force=True)

	if not frappe.db.has_column("Veterinary Patient", "company"):
		frappe.throw("Veterinary Patient Company column was not created.")
	if not frappe.db.has_column("Veterinary Appointment", "company"):
		frappe.throw("Veterinary Appointment Company column was not created.")

	from vetedge.patches.backfill_veterinary_company_context import execute as backfill

	backfill()
