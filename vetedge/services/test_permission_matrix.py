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

FINAL_STATUS_HISTORY_DOCTYPES = (
	"veterinary_consultation/veterinary_consultation.json",
	"veterinary_lab_order/veterinary_lab_order.json",
	"veterinary_vaccination_record/veterinary_vaccination_record.json",
	"veterinary_hospitalisation/veterinary_hospitalisation.json",
	"pet_grooming_session/pet_grooming_session.json",
	"pet_boarding_booking/pet_boarding_booking.json",
	"pet_boarding_stay/pet_boarding_stay.json",
	"veterinary_appointment/veterinary_appointment.json",
)

OPERATIONAL_ACCOUNTING_UNSAFE_FLAGS = ("submit", "cancel", "amend")


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

	def test_cancellation_resolution_keeps_clinical_roles_read_only(self):
		data = json.loads(
			(ROOT / "veterinary_consultation_cancellation_resolution/veterinary_consultation_cancellation_resolution.json").read_text()
		)
		permissions = {row["role"]: row for row in data.get("permissions", [])}

		for role in ("VetEdge Doctor", "VetEdge Front Desk"):
			with self.subTest(role=role):
				self.assertEqual(permissions[role].get("read"), 1)
				self.assertNotEqual(permissions[role].get("write"), 1)
				self.assertNotEqual(permissions[role].get("create"), 1)
				self.assertNotEqual(permissions[role].get("delete"), 1)

		for role in ("System Manager", "VetEdge Administrator", "Branch Manager", "Accounts/Cashier", "Accounts User"):
			with self.subTest(role=role):
				self.assertEqual(permissions[role].get("read"), 1)
				self.assertEqual(permissions[role].get("write"), 1)
				self.assertEqual(permissions[role].get("create"), 1)

	def test_cancellation_resolution_does_not_expose_submit_or_cancel(self):
		data = json.loads(
			(ROOT / "veterinary_consultation_cancellation_resolution/veterinary_consultation_cancellation_resolution.json").read_text()
		)
		for row in data.get("permissions", []):
			with self.subTest(role=row["role"]):
				for flag in OPERATIONAL_ACCOUNTING_UNSAFE_FLAGS:
					self.assertNotEqual(row.get(flag), 1)

	def test_veterinary_settings_write_is_admin_only(self):
		data = json.loads((ROOT / "veterinary_settings/veterinary_settings.json").read_text())
		write_roles = {row["role"] for row in data.get("permissions", []) if row.get("write")}
		read_roles = {row["role"] for row in data.get("permissions", []) if row.get("read")}

		self.assertLessEqual(write_roles, {"System Manager", "VetEdge Administrator"})
		self.assertIn("VetEdge Doctor", read_roles)

	def test_final_status_history_doctypes_do_not_grant_submit_cancel_or_amend(self):
		for relative_path in FINAL_STATUS_HISTORY_DOCTYPES:
			data = json.loads((ROOT / relative_path).read_text())
			for row in data.get("permissions", []):
				with self.subTest(doctype=relative_path, role=row["role"]):
					for flag in OPERATIONAL_ACCOUNTING_UNSAFE_FLAGS:
						self.assertNotEqual(row.get(flag), 1)

	def test_billing_session_accounts_roles_cannot_submit_or_cancel(self):
		data = json.loads((ROOT / "veterinary_billing_session/veterinary_billing_session.json").read_text())
		permissions = {row["role"]: row for row in data.get("permissions", [])}

		self.assertEqual(permissions["Accounts/Cashier"].get("read"), 1)
		self.assertEqual(permissions["Accounts/Cashier"].get("write"), 1)
		self.assertEqual(permissions["Accounts/Cashier"].get("create"), 1)
		self.assertEqual(permissions["Accounts User"].get("read"), 1)
		self.assertNotEqual(permissions["Accounts User"].get("write"), 1)
		for role in ("Accounts/Cashier", "Accounts User"):
			with self.subTest(role=role):
				for flag in OPERATIONAL_ACCOUNTING_UNSAFE_FLAGS:
					self.assertNotEqual(permissions[role].get(flag), 1)
