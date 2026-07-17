from __future__ import annotations

import frappe


def execute():
	replacements = {
		"Draft Invoice Pending": "Unpaid",
		"Draft": "Unpaid",
		"Pending Invoice": "Not Billed",
		"Not Invoiced": "Not Billed",
		"Partially Paid": "Partly Paid",
	}
	if frappe.db.exists("DocType", "Veterinary Consultation"):
		for source, target in replacements.items():
			frappe.db.sql(
				"""
				UPDATE `tabVeterinary Consultation`
				SET payment_status = %s
				WHERE payment_status = %s
				""",
				(target, source),
			)
	if frappe.db.exists("DocType", "Planned Treatment Item"):
		for source, target in replacements.items():
			frappe.db.sql(
				"""
				UPDATE `tabPlanned Treatment Item`
				SET payment_status = %s
				WHERE payment_status = %s
				""",
				(target, source),
			)
