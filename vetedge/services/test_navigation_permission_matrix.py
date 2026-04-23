from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase


VETERINARY_ROOT = Path(__file__).resolve().parents[1] / "veterinary"


EXPECTED_MASTER_ROLE_SETS = {
	"doctype/veterinary_species/veterinary_species.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Front Desk",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"Branch Manager",
	},
	"doctype/veterinary_breed/veterinary_breed.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Front Desk",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"Branch Manager",
	},
	"doctype/veterinary_symptom/veterinary_symptom.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"Branch Manager",
	},
	"doctype/veterinary_diagnosis/veterinary_diagnosis.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"Branch Manager",
	},
	"doctype/veterinary_diagnosis_category/veterinary_diagnosis_category.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"Branch Manager",
	},
	"doctype/veterinary_service_type/veterinary_service_type.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"Dispensary User",
		"Branch Manager",
	},
	"doctype/veterinary_treatment_type/veterinary_treatment_type.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"Dispensary User",
		"Branch Manager",
	},
}


class TestNavigationPermissionMatrix(TestCase):
	def test_remaining_masters_do_not_use_generic_desk_user(self):
		for relative_path in EXPECTED_MASTER_ROLE_SETS:
			with self.subTest(target=relative_path):
				data = json.loads((VETERINARY_ROOT / relative_path).read_text())
				roles = {row["role"] for row in data.get("permissions", [])}
				self.assertNotIn("Desk User", roles)

	def test_remaining_masters_have_expected_explicit_roles(self):
		for relative_path, expected_roles in EXPECTED_MASTER_ROLE_SETS.items():
			with self.subTest(target=relative_path):
				data = json.loads((VETERINARY_ROOT / relative_path).read_text())
				roles = {row["role"] for row in data.get("permissions", [])}
				self.assertEqual(roles, expected_roles)

	def test_veterinary_pages_do_not_use_desk_user(self):
		for relative_path in (
			"page/veterinary_appointment_queue/veterinary_appointment_queue.json",
			"page/veterinary_medical_history/veterinary_medical_history.json",
		):
			with self.subTest(target=relative_path):
				data = json.loads((VETERINARY_ROOT / relative_path).read_text())
				roles = {row["role"] for row in data.get("roles", [])}
				self.assertNotIn("Desk User", roles)

	def test_financial_dashboard_page_has_expected_roles(self):
		data = json.loads(
			(VETERINARY_ROOT / "page/veterinary_financial_dashboard/veterinary_financial_dashboard.json").read_text()
		)
		self.assertEqual(
			{row["role"] for row in data.get("roles", [])},
			{
				"System Manager",
				"VetEdge Administrator",
				"VetEdge Doctor",
				"VetEdge Front Desk",
				"Dispensary User",
				"Branch Manager",
				"Accounts/Cashier",
				"Accounts Manager",
				"Sales Manager",
			},
		)
