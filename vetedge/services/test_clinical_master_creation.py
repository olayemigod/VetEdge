from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services import clinical_master_creation as creation


class TestClinicalMasterCreation(TestCase):
	def test_parse_create_value_round_trip(self):
		value = "__vetedge_create__:diagnosis:Canine Dermatitis"
		self.assertEqual(creation.parse_create_value(value, "diagnosis"), "Canine Dermatitis")
		self.assertIsNone(creation.parse_create_value(value, "symptom"))

	def test_append_create_option_only_when_no_exact_match(self):
		with patch.object(creation, "_kind_allowed", return_value=True):
			rows = creation._append_create_option(
				[{"value": "Vomiting", "label": "Vomiting"}],
				kind="symptom",
				query="Diarrhoea",
				context="consultation",
			)
			exact = creation._append_create_option(
				[{"value": "Vomiting", "label": "Vomiting"}],
				kind="symptom",
				query="vomiting",
				context="consultation",
			)

		self.assertEqual(rows[-1]["value"], "__vetedge_create__:symptom:Diarrhoea")
		self.assertEqual(rows[-1]["create_new"], 1)
		self.assertEqual(len(exact), 1)

	def test_append_create_option_checks_database_exact_match_not_only_current_page(self):
		with (
			patch.object(creation, "_kind_allowed", return_value=True),
			patch.object(creation, "_master_exact_exists", return_value=True),
		):
			rows = creation._append_create_option(
				[{"value": "Different Result", "label": "Different Result"}],
				kind="diagnosis",
				query="Canine Dermatitis",
				context="consultation",
			)

		self.assertEqual(rows, [{"value": "Different Result", "label": "Different Result"}])

	def test_erpnext_item_creation_requires_setting_stock_role_and_item_permission(self):
		with (
			patch.object(creation, "_setting_enabled", return_value=True),
			patch.object(creation, "_roles", return_value={"VetEdge Doctor"}),
			patch.object(creation.frappe, "has_permission", return_value=True),
		):
			self.assertFalse(creation._can_create_erpnext_item())

		with (
			patch.object(creation, "_setting_enabled", return_value=True),
			patch.object(creation, "_roles", return_value={"VetEdge Doctor", "Stock User"}),
			patch.object(creation.frappe, "has_permission", return_value=True),
		):
			self.assertTrue(creation._can_create_erpnext_item())

		with (
			patch.object(creation, "_setting_enabled", return_value=True),
			patch.object(creation, "_roles", return_value={"Stock User"}),
			patch.object(creation.frappe, "has_permission", return_value=False),
		):
			self.assertFalse(creation._can_create_erpnext_item())

	def test_hospitalisation_requires_separate_extension_gate(self):
		def enabled(fieldname: str) -> bool:
			return fieldname == "allow_new_treatment_items_in_clinical_workflow"

		with (
			patch.object(creation, "_setting_enabled", side_effect=enabled),
			patch.object(creation.frappe, "has_permission", return_value=True),
		):
			self.assertFalse(creation._kind_allowed("treatment_item", "hospitalisation"))

	def test_settings_default_off_contract(self):
		settings = json.loads(
			(
				Path(__file__).resolve().parents[1]
				/ "veterinary"
				/ "doctype"
				/ "veterinary_settings"
				/ "veterinary_settings.json"
			).read_text()
		)
		fields = {row.get("fieldname"): row for row in settings.get("fields", [])}

		for fieldname in (
			"allow_new_symptoms_in_clinical_workflow",
			"allow_new_diagnoses_in_clinical_workflow",
			"allow_new_treatment_items_in_clinical_workflow",
			"allow_clinical_master_creation_in_hospitalisation",
			"allow_erpnext_item_creation_from_treatment",
		):
			self.assertIn(fieldname, fields)
			self.assertEqual(fields[fieldname].get("default"), "0")
