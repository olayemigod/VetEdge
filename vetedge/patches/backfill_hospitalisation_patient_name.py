from __future__ import annotations

import frappe


def execute():
	if not frappe.db.exists("DocType", "Veterinary Hospitalisation"):
		return
	if not frappe.db.exists("DocType", "Veterinary Patient"):
		return
	if not frappe.get_meta("Veterinary Hospitalisation").has_field("patient_name"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabVeterinary Hospitalisation` h
		INNER JOIN `tabVeterinary Patient` p ON p.name = h.patient
		SET h.patient_name = COALESCE(NULLIF(p.patient_name, ''), p.name)
		WHERE h.patient IS NOT NULL
			AND h.patient != ''
			AND (h.patient_name IS NULL OR h.patient_name = '' OR h.patient_name != COALESCE(NULLIF(p.patient_name, ''), p.name))
		"""
	)
