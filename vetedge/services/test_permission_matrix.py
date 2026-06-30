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

DOCTOR_WRITABLE_MASTER_DOCTYPES = (
	"consultation_type/consultation_type.json",
	"veterinary_species/veterinary_species.json",
	"veterinary_breed/veterinary_breed.json",
	"veterinary_symptom/veterinary_symptom.json",
	"veterinary_diagnosis/veterinary_diagnosis.json",
	"veterinary_diagnosis_category/veterinary_diagnosis_category.json",
	"veterinary_service_type/veterinary_service_type.json",
	"veterinary_treatment_type/veterinary_treatment_type.json",
	"veterinary_treatment_item/veterinary_treatment_item.json",
	"veterinary_lab_test/veterinary_lab_test.json",
	"veterinary_vaccine/veterinary_vaccine.json",
)


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

	def test_doctor_can_create_and_edit_required_veterinary_masters(self):
		for relative_path in DOCTOR_WRITABLE_MASTER_DOCTYPES:
			with self.subTest(doctype=relative_path):
				data = json.loads((ROOT / relative_path).read_text())
				doctor_perm = next(row for row in data.get("permissions", []) if row["role"] == "VetEdge Doctor")
				self.assertEqual(doctor_perm.get("read"), 1)
				self.assertEqual(doctor_perm.get("create"), 1)
				self.assertEqual(doctor_perm.get("write"), 1)

	def test_billing_session_uses_vetedge_roles_only(self):
		data = json.loads((ROOT / "veterinary_billing_session/veterinary_billing_session.json").read_text())
		roles = {row["role"] for row in data.get("permissions", [])}
		self.assertIn("VetEdge Doctor", roles)
		self.assertIn("VetEdge Administrator", roles)
		self.assertNotIn("VetEdge Manager", roles)
		self.assertNotIn("Reception", roles)
		self.assertNotIn("Cashier", roles)
		self.assertNotIn("Veterinarian", roles)
		self.assertNotIn("Vet Nurse", roles)
