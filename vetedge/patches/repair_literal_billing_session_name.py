import frappe
from frappe.model.naming import make_autoname


BAD_BILLING_SESSION_NAME = "VBS-.YYYY.-.#####"
SERIES = "VBS-.YYYY.-.#####"


def execute():
	if not frappe.db.exists("DocType", "Veterinary Billing Session"):
		return
	if not frappe.db.exists("Veterinary Billing Session", BAD_BILLING_SESSION_NAME):
		return

	new_name = make_autoname(SERIES)
	while frappe.db.exists("Veterinary Billing Session", new_name) or new_name == BAD_BILLING_SESSION_NAME:
		new_name = make_autoname(SERIES)

	frappe.rename_doc(
		"Veterinary Billing Session",
		BAD_BILLING_SESSION_NAME,
		new_name,
		force=True,
		merge=False,
	)
