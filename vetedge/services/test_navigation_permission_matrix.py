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
				"Branch Manager",
				"VetEdge Branch Manager",
				"VetEdge Accounts/Cashier",
				"Accounts/Cashier",
				"Accounts Manager",
				"Sales Manager",
			},
		)

	def test_workspace_sidebar_role_visibility_covers_supported_aliases(self):
		data = json.loads((VETERINARY_ROOT.parent / "workspace_sidebar" / "vetedge.json").read_text())
		display_rules = {
			item.get("label"): item.get("display_depends_on", "")
			for item in data.get("items", [])
			if item.get("display_depends_on")
		}

		self.assertIn("VetEdge Branch Manager", display_rules["Financial Dashboard"])
		self.assertIn("VetEdge Accounts/Cashier", display_rules["Financial Dashboard"])
		self.assertNotIn("VetEdge Front Desk", display_rules["Financial Dashboard"])
		self.assertIn("VetEdge Lab Technician", display_rules["Veterinary Lab Order"])
		self.assertIn("VetEdge Branch Manager", display_rules["Veterinary Lab Order"])
		self.assertIn("VetEdge Lab Technician", display_rules["Veterinary Lab Test"])
		self.assertIn("VetEdge Branch Manager", display_rules["Branch User Assignment"])
		self.assertIn("VetEdge Branch Manager", display_rules["Branch Practitioner Assignment"])

	def test_grooming_doctypes_have_expected_explicit_roles(self):
		expected = {
			"doctype/pet_grooming_service/pet_grooming_service.json": {
				"System Manager",
				"VetEdge Administrator",
				"VetEdge Groomer",
				"VetEdge Front Desk",
				"Branch Manager",
				"VetEdge Branch Manager",
			},
			"doctype/pet_grooming_appointment/pet_grooming_appointment.json": {
				"System Manager",
				"VetEdge Administrator",
				"VetEdge Groomer",
				"VetEdge Front Desk",
				"Branch Manager",
				"VetEdge Branch Manager",
			},
			"doctype/pet_grooming_session/pet_grooming_session.json": {
				"System Manager",
				"VetEdge Administrator",
				"VetEdge Groomer",
				"VetEdge Front Desk",
				"Branch Manager",
				"VetEdge Branch Manager",
			},
		}
		for relative_path, expected_roles in expected.items():
			with self.subTest(target=relative_path):
				data = json.loads((VETERINARY_ROOT / relative_path).read_text())
				roles = {row["role"] for row in data.get("permissions", [])}
				self.assertEqual(roles, expected_roles)

	def test_workspace_sidebar_grooming_links_include_grooming_roles(self):
		data = json.loads((VETERINARY_ROOT.parent / "workspace_sidebar" / "vetedge.json").read_text())
		display_rules = {
			item.get("label"): item.get("display_depends_on", "")
			for item in data.get("items", [])
			if item.get("display_depends_on")
		}
		for label in ("Pet Grooming Service", "Pet Grooming Appointment", "Pet Grooming Session"):
			with self.subTest(label=label):
				self.assertIn("VetEdge Groomer", display_rules[label])
				self.assertIn("VetEdge Branch Manager", display_rules[label])
