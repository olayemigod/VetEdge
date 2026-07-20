from __future__ import annotations

import frappe


FIELDS = (
	{
		"fieldname": "vetedge_context_section",
		"label": "Veterinary Working Context",
		"fieldtype": "Section Break",
		"insert_after": "branch",
		"collapsible": 1,
	},
	{
		"fieldname": "vetedge_company",
		"label": "Veterinary Company",
		"fieldtype": "Link",
		"options": "Company",
		"insert_after": "vetedge_context_section",
		"description": "Company used when this Branch is the active Veterinary working branch.",
	},
	{
		"fieldname": "vetedge_cost_center",
		"label": "Veterinary Cost Center",
		"fieldtype": "Link",
		"options": "Cost Center",
		"insert_after": "vetedge_company",
		"description": "Default cost center for new Veterinary operational and billing documents in this Branch.",
	},
	{
		"fieldname": "vetedge_default_warehouse",
		"label": "Veterinary Default Warehouse",
		"fieldtype": "Link",
		"options": "Warehouse",
		"insert_after": "vetedge_cost_center",
		"description": "Default warehouse or dispensary used by Veterinary stock workflows in this Branch.",
	},
)


def _ensure_custom_field(config: dict) -> None:
	name = f"Branch-{config['fieldname']}"
	if frappe.db.exists("Custom Field", name):
		return
	frappe.get_doc({"doctype": "Custom Field", "dt": "Branch", **config}).insert()


def execute():
	if not frappe.db.exists("DocType", "Branch"):
		return

	for config in FIELDS:
		_ensure_custom_field(config)

	companies = frappe.get_all("Company", pluck="name") if frappe.db.exists("DocType", "Company") else []
	if len(companies) == 1:
		frappe.db.sql(
			"""
			UPDATE `tabBranch`
			SET vetedge_company = %s
			WHERE IFNULL(vetedge_company, '') = ''
			""",
			(companies[0],),
		)

	frappe.clear_cache(doctype="Branch")
