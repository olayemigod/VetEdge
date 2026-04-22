from __future__ import annotations

import frappe


def execute() -> None:
	if not (
		frappe.db.has_column("Veterinary Consultation", "linked_appointment")
		and frappe.db.has_column("Veterinary Consultation", "follow_up_appointment")
		and frappe.db.has_column("Veterinary Appointment", "follow_up_reference")
	):
		return

	rows = frappe.db.sql(
		"""
		SELECT
			consultation.name,
			consultation.linked_appointment
		FROM `tabVeterinary Consultation` consultation
		INNER JOIN `tabVeterinary Appointment` appointment
			ON appointment.name = consultation.linked_appointment
		WHERE IFNULL(consultation.linked_appointment, '') != ''
			AND IFNULL(consultation.follow_up_appointment, '') = ''
			AND appointment.follow_up_reference = consultation.name
		""",
		as_dict=True,
	)

	for row in rows:
		frappe.db.set_value(
			"Veterinary Consultation",
			row.name,
			{
				"follow_up_appointment": row.linked_appointment,
				"linked_appointment": None,
			},
			update_modified=False,
		)
