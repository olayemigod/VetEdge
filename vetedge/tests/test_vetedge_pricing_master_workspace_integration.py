from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from vetedge.services.pricing_master_workspace import (
	get_pricing_master_definition,
	get_pricing_master_document,
	get_pricing_master_link_options,
	get_pricing_master_list,
	save_pricing_master_document,
)


class TestVetEdgePricingMasterWorkspaceIntegration(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def unique(self, prefix: str) -> str:
		return f"{prefix}-{frappe.generate_hash(length=8)}"

	def make_item(self, prefix: str, *, is_stock_item: int, disabled: int = 0):
		item_code = self.unique(prefix)
		return frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": item_code,
				"item_group": "All Item Groups",
				"stock_uom": "Nos",
				"is_stock_item": is_stock_item,
				"is_sales_item": 1,
				"disabled": disabled,
			}
		).insert(ignore_permissions=True)

	def delete_if_exists(self, doctype: str, name: str | None) -> None:
		if name and frappe.db.exists(doctype, name):
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)

	def test_all_phase_2b_definitions_and_lists_are_permission_aware(self):
		for resource, doctype in (
			("treatment-items", "Veterinary Treatment Item"),
			("treatment-types", "Veterinary Treatment Type"),
			("lab-tests", "Veterinary Lab Test"),
			("vaccines", "Veterinary Vaccine"),
			("grooming-services", "Pet Grooming Service"),
		):
			with self.subTest(resource=resource):
				definition = get_pricing_master_definition(resource)
				self.assertEqual(definition["doctype"], doctype)
				self.assertTrue(definition["permissions"]["read"])
				self.assertTrue(definition["columns"])
				self.assertTrue(definition["notice"])
				payload = get_pricing_master_list(resource, page_length=5)
				self.assertEqual(payload["page_length"], 5)
				self.assertIn("rows", payload)
				self.assertIn("total", payload)

	def test_forms_preserve_sections_and_lock_identity_after_insert(self):
		new_payload = get_pricing_master_document("lab-tests")
		self.assertTrue(new_payload["schema"]["tabs"])
		sections = [section for tab in new_payload["schema"]["tabs"] for section in tab["sections"]]
		self.assertGreaterEqual(len(sections), 3)
		new_fields = {field["fieldname"]: field for section in sections for field in section["fields"]}
		self.assertFalse(new_fields["test_name"]["read_only"])

		name = self.unique("EdgeSuite Lab Test")
		doc = frappe.get_doc(
			{
				"doctype": "Veterinary Lab Test",
				"test_name": name,
				"is_active": 1,
				"result_format": "Value Driven",
			}
		).insert(ignore_permissions=True)
		try:
			existing = get_pricing_master_document("lab-tests", doc.name)
			fields = {
				field["fieldname"]: field
				for tab in existing["schema"]["tabs"]
				for section in tab["sections"]
				for field in section["fields"]
			}
			self.assertTrue(fields["test_name"]["read_only"])
		finally:
			self.delete_if_exists("Veterinary Lab Test", doc.name)

	def test_item_link_filters_distinguish_stock_and_non_stock_billing_items(self):
		marker = self.unique("EdgeSuite Pricing Item")
		non_stock = self.make_item(f"{marker}-Service", is_stock_item=0)
		stock = self.make_item(f"{marker}-Stock", is_stock_item=1)
		disabled = self.make_item(f"{marker}-Disabled", is_stock_item=0, disabled=1)
		try:
			lab_values = {
				row["value"]
				for row in get_pricing_master_link_options("lab-tests", "linked_item", query=marker)
			}
			self.assertIn(non_stock.name, lab_values)
			self.assertNotIn(stock.name, lab_values)
			self.assertNotIn(disabled.name, lab_values)

			vaccine_values = {
				row["value"]
				for row in get_pricing_master_link_options("vaccines", "default_item", query=marker)
			}
			self.assertIn(non_stock.name, vaccine_values)
			self.assertIn(stock.name, vaccine_values)
			self.assertNotIn(disabled.name, vaccine_values)

			with self.assertRaises(frappe.ValidationError):
				save_pricing_master_document(
					"lab-tests",
					{
						"test_name": self.unique("Blocked Stock Lab"),
						"is_active": 1,
						"result_format": "Value Driven",
						"linked_item": stock.name,
					},
				)

			with self.assertRaises(frappe.ValidationError):
				save_pricing_master_document(
					"grooming-services",
					{
						"service_name": self.unique("Blocked Stock Grooming"),
						"default_item": stock.name,
						"is_active": 1,
					},
				)
		finally:
			for item in (non_stock, stock, disabled):
				self.delete_if_exists("Item", item.name)

	def test_treatment_item_save_preserves_controller_price_and_shelf_life_side_effects(self):
		item = self.make_item("EdgeSuite Treatment Item", is_stock_item=1)
		master_name = None
		item_price_name = None
		try:
			created = save_pricing_master_document(
				"treatment-items",
				{
					"item": item.name,
					"price_list": "Standard Selling",
					"default_price": 125.5,
					"shelf_life_in_days": 45,
					"disabled": 0,
				},
			)
			master_name = created["name"]
			self.assertEqual(created["values"]["item"], item.name)
			self.assertEqual(frappe.db.get_value("Item", item.name, "shelf_life_in_days"), 45)
			item_price_name = frappe.db.get_value(
				"Item Price",
				{"item_code": item.name, "price_list": "Standard Selling"},
				"name",
			)
			self.assertTrue(item_price_name)
			self.assertEqual(float(frappe.db.get_value("Item Price", item_price_name, "price_list_rate")), 125.5)
		finally:
			self.delete_if_exists("Veterinary Treatment Item", master_name)
			self.delete_if_exists("Item Price", item_price_name)
			self.delete_if_exists("Item", item.name)

	def test_identity_fields_are_immutable_and_stale_updates_are_blocked(self):
		original_name = self.unique("EdgeSuite Treatment Type")
		created = save_pricing_master_document(
			"treatment-types",
			{
				"treatment_type_name": original_name,
				"treatment_category": "Procedure",
				"requires_dispensary": 0,
				"disabled": 0,
			},
		)
		try:
			updated = save_pricing_master_document(
				"treatment-types",
				{
					**created["values"],
					"treatment_type_name": self.unique("Attempted Rename"),
					"description": "Identity remained stable.",
				},
				name=created["name"],
				modified=str(created["modified"]),
			)
			self.assertEqual(updated["values"]["treatment_type_name"], original_name)
			with self.assertRaises(frappe.TimestampMismatchError):
				save_pricing_master_document(
					"treatment-types",
					updated["values"],
					name=created["name"],
					modified="1900-01-01 00:00:00.000000",
				)
		finally:
			self.delete_if_exists("Veterinary Treatment Type", created["name"])

	def test_inactive_species_and_negative_values_are_rejected(self):
		species_name = self.unique("Inactive Vaccine Species")
		species = frappe.get_doc(
			{
				"doctype": "Veterinary Species",
				"species_name": species_name,
				"disabled": 1,
			}
		).insert(ignore_permissions=True)
		try:
			with self.assertRaises(frappe.ValidationError):
				save_pricing_master_document(
					"vaccines",
					{
						"vaccine_name": self.unique("Blocked Vaccine"),
						"species": species.name,
						"is_active": 1,
					},
				)
		finally:
			self.delete_if_exists("Veterinary Species", species.name)

		for resource, values in (
			("treatment-items", {"item": "Missing Item", "default_price": -1}),
			("lab-tests", {"test_name": self.unique("Negative Lab"), "default_rate": -1}),
			("vaccines", {"vaccine_name": self.unique("Negative Vaccine"), "default_next_due_days": -1}),
			("grooming-services", {"service_name": self.unique("Negative Grooming"), "estimated_duration": -1}),
		):
			with self.subTest(resource=resource), self.assertRaises(frappe.ValidationError):
				save_pricing_master_document(resource, values)
