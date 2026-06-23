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
				"Accounts/Cashier",
				"Accounts Manager",
				"Sales Manager",
			},
		)

	def test_workspace_sidebar_role_visibility_uses_canonical_roles(self):
		data = json.loads((VETERINARY_ROOT.parent / "workspace_sidebar" / "vetedge.json").read_text())
		display_rules = {
			item.get("label"): item.get("display_depends_on", "")
			for item in data.get("items", [])
			if item.get("display_depends_on")
		}

		self.assertIn("Branch Manager", display_rules["Financial Dashboard"])
		self.assertIn("Accounts/Cashier", display_rules["Financial Dashboard"])
		self.assertNotIn("VetEdge Front Desk", display_rules["Financial Dashboard"])
		self.assertIn("Lab Technician", display_rules["Lab Orders"])
		self.assertIn("Branch Manager", display_rules["Lab Orders"])
		self.assertIn("Lab Technician", display_rules["Lab Tests"])
		self.assertIn("Branch Manager", display_rules["Branch User Assignment"])
		self.assertIn("Branch Manager", display_rules["Branch Practitioner Assignment"])
		for alias in (
			"VetEdge Branch Manager",
			"VetEdge Accounts/Cashier",
			"VetEdge Lab Technician",
		):
			self.assertNotIn(alias, json.dumps(display_rules))

	def test_grooming_doctypes_have_expected_explicit_roles(self):
		expected = {
			"doctype/pet_grooming_service/pet_grooming_service.json": {
				"System Manager",
				"VetEdge Administrator",
				"VetEdge Groomer",
				"VetEdge Front Desk",
				"Branch Manager",
			},
			"doctype/pet_grooming_appointment/pet_grooming_appointment.json": {
				"System Manager",
				"VetEdge Administrator",
				"VetEdge Groomer",
				"VetEdge Front Desk",
				"Branch Manager",
			},
			"doctype/pet_grooming_session/pet_grooming_session.json": {
				"System Manager",
				"VetEdge Administrator",
				"VetEdge Groomer",
				"VetEdge Front Desk",
				"Branch Manager",
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
				self.assertIn("Branch Manager", display_rules[label])
				self.assertNotIn("VetEdge Branch Manager", display_rules[label])

	def test_vaccination_doctypes_use_canonical_nurse_role(self):
		for relative_path in (
			"doctype/veterinary_vaccine/veterinary_vaccine.json",
			"doctype/veterinary_vaccination_record/veterinary_vaccination_record.json",
		):
			with self.subTest(target=relative_path):
				data = json.loads((VETERINARY_ROOT / relative_path).read_text())
				roles = {row["role"] for row in data.get("permissions", [])}
				self.assertIn("Veterinary Nurse", roles)
				self.assertNotIn("VetEdge Nurse", roles)

	def test_boarding_doctypes_use_canonical_branch_manager_role(self):
		for relative_path in (
			"doctype/pet_boarding_booking/pet_boarding_booking.json",
			"doctype/pet_boarding_stay/pet_boarding_stay.json",
			"doctype/pet_boarding_care_record/pet_boarding_care_record.json",
			"doctype/kennel/kennel.json",
			"doctype/kennel_availability/kennel_availability.json",
		):
			with self.subTest(target=relative_path):
				data = json.loads((VETERINARY_ROOT / relative_path).read_text())
				roles = {row["role"] for row in data.get("permissions", [])}
				self.assertIn("Branch Manager", roles)
				self.assertNotIn("VetEdge Branch Manager", roles)
