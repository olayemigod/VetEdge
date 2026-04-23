from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


BRANCH_COST_CENTER_FIELD = "vetedge_cost_center"
BRANCH_DISPENSARY_WAREHOUSE_FIELD = "vetedge_dispensary_warehouse"
STOCK_ENTRY_CONSULTATION_FIELD = "vetedge_consultation"


def ensure_custom_fields() -> None:
	ensure_branch_custom_fields()
	ensure_stock_entry_custom_fields()


def ensure_branch_custom_fields() -> None:
	if not frappe.db.exists("DocType", "Branch"):
		return

	branch_meta = frappe.get_meta("Branch")
	fields = []

	if not branch_meta.has_field("cost_center") and not branch_meta.has_field(BRANCH_COST_CENTER_FIELD):
		fields.append(
			{
				"fieldname": BRANCH_COST_CENTER_FIELD,
				"fieldtype": "Link",
				"insert_after": "branch",
				"label": "VetEdge Cost Center",
				"options": "Cost Center",
			}
		)

	if not branch_meta.has_field("warehouse") and not branch_meta.has_field(BRANCH_DISPENSARY_WAREHOUSE_FIELD):
		fields.append(
			{
				"fieldname": BRANCH_DISPENSARY_WAREHOUSE_FIELD,
				"fieldtype": "Link",
				"insert_after": BRANCH_COST_CENTER_FIELD if fields else "branch",
				"label": "VetEdge Dispensary Warehouse",
				"options": "Warehouse",
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
