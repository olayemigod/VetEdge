from __future__ import annotations

import frappe


def execute():
	if not frappe.db.exists("DocType", "Veterinary Patient"):
		return
	if not frappe.db.has_column("Veterinary Patient", "company"):
		return
	if not frappe.db.exists("DocType", "Branch"):
		return
	if not frappe.get_meta("Branch").has_field("vetedge_company"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabVeterinary Patient` p
		INNER JOIN `tabBranch` b ON b.name = p.default_branch
		SET p.company = b.vetedge_company
		WHERE IFNULL(p.company, '') = ''
			AND IFNULL(p.default_branch, '') != ''
			AND IFNULL(b.vetedge_company, '') != ''
		"""
	)

	if frappe.db.exists("DocType", "Veterinary Appointment") and frappe.db.has_column(
		"Veterinary Appointment", "company"
	):
		frappe.db.sql(
			"""
			UPDATE `tabVeterinary Appointment` a
			INNER JOIN `tabVeterinary Patient` p ON p.name = a.patient
			SET a.company = p.company
			WHERE IFNULL(a.company, '') = ''
				AND IFNULL(p.company, '') != ''
			"""
		)
