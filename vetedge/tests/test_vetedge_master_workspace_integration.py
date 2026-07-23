from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from vetedge.services.master_workspace import (
	get_master_definition,
	get_master_document,
	get_master_link_options,
	get_master_list,
	save_master_document,
)


class TestVetEdgeMasterWorkspaceIntegration(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def unique(self, prefix: str) -> str:
		return f"{prefix}-{frappe.generate_hash(length=8)}"

	def test_all_phase_2a_master_definitions_are_permission_aware(self):
		for resource, doctype in (
			("species", "Veterinary Species"),
			("breeds", "Veterinary Breed"),
			("symptoms", "Veterinary Symptom"),
			("diagnosis-categories", "Veterinary Diagnosis Category"),
			("diagnoses", "Veterinary Diagnosis"),
			("service-types", "Veterinary Service Type"),
			("consultation-types", "Consultation Type"),
		):
			with self.subTest(resource=resource):
				definition = get_master_definition(resource)
				self.assertEqual(definition["resource"], resource)
				self.assertEqual(definition["doctype"], doctype)
				self.assertTrue(definition["permissions"]["read"])
				self.assertTrue(definition["columns"])

	def test_new_master_forms_resolve_complete_metadata(self):
		for resource in (
			"species",
			"breeds",
			"symptoms",
			"diagnosis-categories",
			"diagnoses",
			"service-types",
			"consultation-types",
		):
			with self.subTest(resource=resource):
				payload = get_master_document(resource)
				self.assertTrue(payload["is_new"])
				self.assertTrue(payload["schema"]["tabs"])
				self.assertIsInstance(payload["values"], dict)
				self.assertTrue(payload["permissions"]["create"])

	def test_permission_aware_lists_return_pagination_contract(self):
		for resource in (
			"species",
			"breeds",
			"symptoms",
			"diagnosis-categories",
			"diagnoses",
			"service-types",
			"consultation-types",
		):
			with self.subTest(resource=resource):
				payload = get_master_list(resource, page_length=5)
				for key in ("rows", "total", "start", "page_length"):
					self.assertIn(key, payload)
				self.assertEqual(payload["start"], 0)
				self.assertEqual(payload["page_length"], 5)

	def test_species_round_trip_uses_normal_document_save(self):
		species_name = self.unique("EdgeSuite Species")
		created_name = None
		try:
			created = save_master_document(
				"species",
				{
					"species_name": species_name,
					"description": "Created through the EdgeSuite clinical master workspace test.",
					"disabled": 0,
				},
			)
			created_name = created["name"]
			self.assertEqual(created["values"]["species_name"], species_name)
			self.assertEqual(created["state"], "Active")

			updated = save_master_document(
				"species",
				{
					**created["values"],
					"description": "Updated safely through the EdgeSuite master workspace.",
				},
				name=created_name,
				modified=str(created["modified"]),
			)
			self.assertEqual(
				updated["values"]["description"],
				"Updated safely through the EdgeSuite master workspace.",
			)
		finally:
			if created_name and frappe.db.exists("Veterinary Species", created_name):
				frappe.delete_doc("Veterinary Species", created_name, force=True, ignore_permissions=True)

	def test_disabled_species_is_hidden_and_rejected_for_breed(self):
		marker = self.unique("EdgeSuite Link Species")
		active_name = f"{marker}-Active"
		disabled_name = f"{marker}-Disabled"
		active = frappe.get_doc(
			{
				"doctype": "Veterinary Species",
				"species_name": active_name,
				"disabled": 0,
			}
		).insert(ignore_permissions=True)
		disabled = frappe.get_doc(
			{
				"doctype": "Veterinary Species",
				"species_name": disabled_name,
				"disabled": 1,
			}
		).insert(ignore_permissions=True)
		try:
			options = get_master_link_options("breeds", "species", query=marker)
			values = {row["value"] for row in options}
			self.assertIn(active.name, values)
			self.assertNotIn(disabled.name, values)

			with self.assertRaises(frappe.ValidationError):
				save_master_document(
					"breeds",
					{
						"breed_name": self.unique("Blocked Breed"),
						"species": disabled.name,
						"disabled": 0,
					},
				)
		finally:
			for name in (active.name, disabled.name):
				if frappe.db.exists("Veterinary Species", name):
					frappe.delete_doc("Veterinary Species", name, force=True, ignore_permissions=True)

	def test_stale_master_update_is_blocked(self):
		symptom_name = self.unique("EdgeSuite Symptom")
		doc = frappe.get_doc(
			{
				"doctype": "Veterinary Symptom",
				"symptom_name": symptom_name,
				"body_system": "General",
				"disabled": 0,
			}
		).insert(ignore_permissions=True)
		try:
			with self.assertRaises(frappe.TimestampMismatchError):
				save_master_document(
					"symptoms",
					{
						"symptom_name": symptom_name,
						"body_system": "Digestive",
						"disabled": 0,
					},
					name=doc.name,
					modified="1900-01-01 00:00:00.000000",
				)
		finally:
			if frappe.db.exists("Veterinary Symptom", doc.name):
				frappe.delete_doc("Veterinary Symptom", doc.name, force=True, ignore_permissions=True)

	def test_negative_rates_and_sort_orders_are_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			save_master_document(
				"service-types",
				{
					"service_type_name": self.unique("Invalid Service"),
					"standard_rate": -1,
					"disabled": 0,
				},
			)

		with self.assertRaises(frappe.ValidationError):
			save_master_document(
				"consultation-types",
				{
					"consultation_type": self.unique("Invalid Consultation"),
					"sort_order": -1,
					"disabled": 0,
				},
			)
