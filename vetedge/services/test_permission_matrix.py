from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1] / "veterinary" / "doctype"


EXPECTED_ROLE_SETS = {
	"veterinary_patient/veterinary_patient.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Front Desk",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"Branch Manager",
		"Dispensary User",
		"Lab Technician",
	},
	"veterinary_consultation/veterinary_consultation.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"VetEdge Front Desk",
		"Veterinary Nurse",
		"Branch Manager",
		"Dispensary User",
	},
	"veterinary_vital_signs/veterinary_vital_signs.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"Branch Manager",
	},
	"veterinary_treatment_item/veterinary_treatment_item.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"VetEdge Front Desk",
		"Veterinary Nurse",
		"Dispensary User",
		"Lab Technician",
		"Branch Manager",
	},
}


class TestPermissionMatrix(TestCase):
	def test_protected_clinical_doctypes_do_not_use_generic_desk_user(self):
		for relative_path in EXPECTED_ROLE_SETS:
			with self.subTest(doctype=relative_path):
				data = json.loads((ROOT / relative_path).read_text())
				roles = {row["role"] for row in data.get("permissions", [])}
				self.assertNotIn("Desk User", roles)

	def test_protected_clinical_doctypes_have_expected_role_sets(self):
		for relative_path, expected_roles in EXPECTED_ROLE_SETS.items():
			with self.subTest(doctype=relative_path):
				data = json.loads((ROOT / relative_path).read_text())
				roles = {row["role"] for row in data.get("permissions", [])}
				self.assertEqual(roles, expected_roles)
