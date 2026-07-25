from __future__ import annotations

import frappe


INVALID_STATUS = "Completed"
PENDING_DISPENSARY = "Pending Dispensary"


def execute() -> None:
	"""Reopen impossible completed consultations that still require dispensary confirmation."""
	if not frappe.db.exists("DocType", "Veterinary Consultation"):
		return

	rows = frappe.get_all(
		"Veterinary Consultation",
		filters={
			"status": INVALID_STATUS,
			"dispensary_status": PENDING_DISPENSARY,
		},
		pluck="name",
	)
	for consultation in rows:
		frappe.db.set_value(
			"Veterinary Consultation",
			consultation,
			"status",
			PENDING_DISPENSARY,
			update_modified=True,
		)
		frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Info",
				"reference_doctype": "Veterinary Consultation",
				"reference_name": consultation,
				"content": (
					"VetEdge migration corrected an invalid Completed consultation that still had "
					"Pending Dispensary status. The consultation was returned to Pending Dispensary "
					"so dispensing can be reviewed and confirmed safely."
				),
			}
		).insert(ignore_permissions=True)
