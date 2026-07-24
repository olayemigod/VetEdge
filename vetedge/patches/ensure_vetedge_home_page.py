from __future__ import annotations

import frappe

PAGE_NAME = "vetedge"
PAGE_ROLES = (
	"System Manager",
	"VetEdge Administrator",
	"VetEdge Doctor",
	"Veterinary Nurse",
	"VetEdge Front Desk",
	"Branch Manager",
	"VetEdge Branch Manager",
	"Dispensary User",
)


def execute() -> None:
	"""Create or repair the stable `/app/vetedge` Desk Page idempotently."""
	if not frappe.db.exists("DocType", "Page"):
		return

	if frappe.db.exists("Page", PAGE_NAME):
		page = frappe.get_doc("Page", PAGE_NAME)
	else:
		page = frappe.get_doc(
			{
				"doctype": "Page",
				"name": PAGE_NAME,
				"page_name": PAGE_NAME,
				"title": "Veterinary Home",
				"module": "Veterinary",
				"standard": "Yes",
				"system_page": 0,
			}
		)

	changed = page.is_new()
	for fieldname, value in (
		("page_name", PAGE_NAME),
		("title", "Veterinary Home"),
		("module", "Veterinary"),
		("standard", "Yes"),
		("system_page", 0),
	):
		if page.get(fieldname) != value:
			page.set(fieldname, value)
			changed = True

	existing_roles = {row.role for row in page.get("roles") or [] if row.role}
	for role in PAGE_ROLES:
		if role not in existing_roles and frappe.db.exists("Role", role):
			page.append("roles", {"role": role})
			changed = True

	if page.is_new():
		page.insert(ignore_permissions=True)
	elif changed:
		page.save(ignore_permissions=True)

	frappe.clear_cache(doctype="Page")
