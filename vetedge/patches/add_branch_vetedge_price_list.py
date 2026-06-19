import frappe


def execute():
	if not frappe.db.exists("DocType", "Branch"):
		return
	if frappe.db.exists("Custom Field", "Branch-vetedge_price_list"):
		return
	frappe.get_doc(
		{
			"doctype": "Custom Field",
			"dt": "Branch",
			"fieldname": "vetedge_price_list",
			"label": "VetEdge Price List",
			"fieldtype": "Link",
			"options": "Price List",
			"description": "Selling price list used by VetEdge Billing Core for this branch. If blank, Billing Core uses the default selling price list.",
			"insert_after": "cost_center",
		}
	).insert()
