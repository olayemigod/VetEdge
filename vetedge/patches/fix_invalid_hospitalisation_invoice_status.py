from __future__ import annotations

import frappe


def execute():
	if not frappe.db.exists("DocType", "Veterinary Hospitalisation"):
		return
	valid = {"Not Invoiced", "Draft", "Unpaid", "Partly Paid", "Paid", "Overdue", "Cancelled"}
	replacements = {
		"Draft Invoice Pending": "Draft",
		"Pending Invoice": "Not Invoiced",
		"Partially Paid": "Partly Paid",
	}
	for source, target in replacements.items():
		if target in valid:
			frappe.db.sql(
				"""
				UPDATE `tabVeterinary Hospitalisation`
				SET invoice_status = %s
				WHERE invoice_status = %s
				""",
				(target, source),
			)
