from __future__ import annotations

import frappe


PAGE_ROLES = {
	"vetedge": (
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"VetEdge Nurse",
		"VetEdge Front Desk",
		"Branch Manager",
		"VetEdge Branch Manager",
		"Dispensary User",
	),
	"vetedge-clinical-workspace": (
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"VetEdge Nurse",
		"VetEdge Front Desk",
		"Branch Manager",
		"VetEdge Branch Manager",
		"Dispensary User",
	),
}


def execute() -> None:
	"""Add operational role aliases to existing VetEdge Desk Pages idempotently."""
	if not frappe.db.exists("DocType", "Page"):
		return

	changed = False
	for page_name, roles in PAGE_ROLES.items():
		if not frappe.db.exists("Page", page_name):
			continue
		page = frappe.get_doc("Page", page_name)
		existing_roles = {row.role for row in page.get("roles") or [] if row.role}
		page_changed = False
		for role in roles:
			if role in existing_roles or not frappe.db.exists("Role", role):
				continue
			page.append("roles", {"role": role})
			page_changed = True
		if page_changed:
			page.save(ignore_permissions=True)
			changed = True

	if changed:
		frappe.clear_cache(doctype="Page")
