from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


BRANCH_COST_CENTER_FIELD = "vetedge_cost_center"
BRANCH_DISPENSARY_WAREHOUSE_FIELD = "vetedge_dispensary_warehouse"
BRANCH_NADIS_ADMIN_LEVEL_1_FIELD = "vetedge_nadis_admin_level_1"
BRANCH_NADIS_ADMIN_LEVEL_2_FIELD = "vetedge_nadis_admin_level_2"
STOCK_ENTRY_CONSULTATION_FIELD = "vetedge_consultation"


def ensure_custom_fields() -> None:
	ensure_branch_custom_fields()
	ensure_stock_entry_custom_fields()


def ensure_branch_custom_fields() -> None:
	if not frappe.db.exists("DocType", "Branch"):
		return

	branch_meta = frappe.get_meta("Branch")
	fields = []
	insert_after = "branch"

	if not branch_meta.has_field("cost_center") and not branch_meta.has_field(BRANCH_COST_CENTER_FIELD):
		fields.append(
			{
				"fieldname": BRANCH_COST_CENTER_FIELD,
				"fieldtype": "Link",
				"insert_after": insert_after,
				"label": "VetEdge Cost Center",
				"options": "Cost Center",
			}
		)
		insert_after = BRANCH_COST_CENTER_FIELD
	elif branch_meta.has_field(BRANCH_COST_CENTER_FIELD):
		insert_after = BRANCH_COST_CENTER_FIELD

	if not branch_meta.has_field("warehouse") and not branch_meta.has_field(BRANCH_DISPENSARY_WAREHOUSE_FIELD):
		fields.append(
			{
				"fieldname": BRANCH_DISPENSARY_WAREHOUSE_FIELD,
				"fieldtype": "Link",
				"insert_after": insert_after,
				"label": "VetEdge Dispensary Warehouse",
				"options": "Warehouse",
			}
		)
		insert_after = BRANCH_DISPENSARY_WAREHOUSE_FIELD
	elif branch_meta.has_field(BRANCH_DISPENSARY_WAREHOUSE_FIELD):
		insert_after = BRANCH_DISPENSARY_WAREHOUSE_FIELD

	if not branch_meta.has_field(BRANCH_NADIS_ADMIN_LEVEL_1_FIELD):
		fields.append(
			{
				"description": "Exact Admin Division Level 1 value required by the official NADIS/VCN workbook, for example Lagos, Nigeria.",
				"fieldname": BRANCH_NADIS_ADMIN_LEVEL_1_FIELD,
				"fieldtype": "Data",
				"insert_after": insert_after,
				"label": "NADIS State / Admin Level 1",
			}
		)
		insert_after = BRANCH_NADIS_ADMIN_LEVEL_1_FIELD
	else:
		insert_after = BRANCH_NADIS_ADMIN_LEVEL_1_FIELD

	if not branch_meta.has_field(BRANCH_NADIS_ADMIN_LEVEL_2_FIELD):
		fields.append(
			{
				"description": "Exact Admin Division Level 2 value required by the official NADIS/VCN workbook, normally the LGA reporting value.",
				"fieldname": BRANCH_NADIS_ADMIN_LEVEL_2_FIELD,
				"fieldtype": "Data",
				"insert_after": insert_after,
				"label": "NADIS LGA / Admin Level 2",
			}
		)

	if fields:
		create_custom_fields({"Branch": fields}, update=True)


def ensure_stock_entry_custom_fields() -> None:
	if not frappe.db.exists("DocType", "Stock Entry"):
		return

	stock_entry_meta = frappe.get_meta("Stock Entry")
	if stock_entry_meta.has_field(STOCK_ENTRY_CONSULTATION_FIELD):
		return

	create_custom_fields(
		{
			"Stock Entry": [
				{
					"fieldname": STOCK_ENTRY_CONSULTATION_FIELD,
					"fieldtype": "Link",
					"insert_after": "branch",
					"label": "Veterinary Consultation",
					"options": "Veterinary Consultation",
					"read_only": 1,
				}
			]
		},
		update=True,
	)
