import frappe


def execute():
	"""Keep the internal VetEdge identity stable while normalizing the visible Desk label."""
	if not frappe.db.exists("DocType", "Desktop Icon"):
		return

	for icon_name in ("VetEdge", "Veterinary"):
		if not frappe.db.exists("Desktop Icon", icon_name):
			continue
		if frappe.db.get_value("Desktop Icon", icon_name, "label") != "Veterinary":
			frappe.db.set_value(
				"Desktop Icon",
				icon_name,
				"label",
				"Veterinary",
				update_modified=False,
			)
