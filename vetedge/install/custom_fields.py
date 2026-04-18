from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


BRANCH_COST_CENTER_FIELD = "vetedge_cost_center"


def ensure_custom_fields() -> None:
	ensure_branch_cost_center_field()


def ensure_branch_cost_center_field() -> None:
	if not frappe.db.exists("DocType", "Branch"):
		return

	branch_meta = frappe.get_meta("Branch")
	if branch_meta.has_field("cost_center") or branch_meta.has_field(BRANCH_COST_CENTER_FIELD):
		return

	create_custom_fields(
		{
			"Branch": [
				{
					"fieldname": BRANCH_COST_CENTER_FIELD,
					"fieldtype": "Link",
					"insert_after": "branch",
					"label": "VetEdge Cost Center",
					"options": "Cost Center",
				}
			]
		},
		update=True,
	)
