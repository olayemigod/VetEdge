from __future__ import annotations

import frappe


no_cache = 1
no_login_required = True


def get_context(context):
	context.title = "Register Your Pet"
	context.branches = frappe.get_all("Branch", fields=["name"], order_by="name asc")
	context.species = frappe.get_all(
		"Veterinary Species",
		filters={"disabled": ["!=", 1]} if frappe.get_meta("Veterinary Species").has_field("disabled") else {},
		fields=["name", "species_name"],
		order_by="species_name asc",
	)
	return context
