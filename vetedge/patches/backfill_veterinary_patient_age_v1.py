from __future__ import annotations

import frappe

from vetedge.services.age import calculate_age_label


def execute() -> None:
	if not frappe.db.exists("DocType", "Veterinary Patient"):
		return
	meta = frappe.get_meta("Veterinary Patient")
	if not meta.has_field("date_of_birth") or not meta.has_field("approximate_age"):
		return
	rows = frappe.get_all(
		"Veterinary Patient",
		filters={"date_of_birth": ["is", "set"]},
		fields=["name", "date_of_birth", "approximate_age"],
		limit_page_length=0,
	)
	for row in rows:
		age = calculate_age_label(row.date_of_birth)
		if age and row.approximate_age != age:
			frappe.db.set_value(
				"Veterinary Patient",
				row.name,
				"approximate_age",
				age,
				update_modified=False,
			)
