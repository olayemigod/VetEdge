from __future__ import annotations

import frappe


LEGACY_DIAGNOSIS_TYPE_MAP = {
	"Primary": "Working",
	"Rule Out": "Ruled Out",
	"Resolved": "Others",
}
VALID_DIAGNOSIS_TYPES = {
	"Differential",
	"Confirmed/Definitive",
	"Working",
	"Presumptive",
	"Ruled Out",
	"Others",
}


def execute() -> None:
	"""Normalize legacy diagnosis classifications without changing clinical notes.

	The old values mixed certainty and outcome concepts. Ambiguous legacy
	"Resolved" values are preserved under "Others" rather than being promoted to
	a definitive diagnosis. The patch is idempotent and touches only the diagnosis
	classification field on the child row.
	"""
	if not frappe.db.exists("DocType", "Consultation Diagnosis"):
		return

	for old_value, new_value in LEGACY_DIAGNOSIS_TYPE_MAP.items():
		frappe.db.sql(
			"""
			UPDATE `tabConsultation Diagnosis`
			SET diagnosis_type = %s
			WHERE diagnosis_type = %s
			""",
			(new_value, old_value),
		)

	# Preserve unexpected historical values instead of silently discarding them.
	placeholders = ", ".join(["%s"] * len(VALID_DIAGNOSIS_TYPES))
	frappe.db.sql(
		f"""
		UPDATE `tabConsultation Diagnosis`
		SET diagnosis_type = 'Others'
		WHERE IFNULL(diagnosis_type, '') != ''
		  AND diagnosis_type NOT IN ({placeholders})
		""",
		tuple(sorted(VALID_DIAGNOSIS_TYPES)),
	)
