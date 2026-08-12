from __future__ import annotations

import unittest
from unittest.mock import patch

from vetedge.services import service_revenue


class TestServiceRevenue(unittest.TestCase):
	def test_consultation_setting_outranks_treatment_master(self):
		settings = {
			"consultation_item": "CONSULT-ITEM",
			"default_registration_item": "REG-ITEM",
			"default_boarding_billing_item": "",
			"hospitalisation_admission_fee_item": "",
		}

		def single_value(fieldname):
			return settings.get(fieldname, "")

		def pluck_items(doctype, _fieldname):
			if doctype == "Veterinary Treatment Item":
				return {"CONSULT-ITEM", "TREATMENT-ITEM"}
			return set()

		with (
			patch.object(service_revenue, "_single_value", side_effect=single_value),
			patch.object(service_revenue, "_pluck_items", side_effect=pluck_items),
		):
			mapping = service_revenue.configured_item_categories()

		self.assertEqual(mapping["CONSULT-ITEM"], "Consultation Service")
		self.assertEqual(mapping["TREATMENT-ITEM"], "Treatment")
		self.assertEqual(mapping["REG-ITEM"], "Registration")

	def test_legacy_consultation_description_outranks_generic_treatment_mapping(self):
		category = service_revenue.classify_service_line(
			"OLD-CONSULT",
			"Consultation Fee",
			{"OLD-CONSULT": "Treatment"},
		)
		self.assertEqual(category, "Consultation Service")

	def test_consultation_practitioner_falls_back_to_user_full_name(self):
		class Meta:
			@staticmethod
			def get_field(fieldname):
				return fieldname in {"consulting_practitioner_name", "consulting_practitioner"}

		def get_all(doctype, filters=None, fields=None, **_kwargs):
			if doctype == "Veterinary Consultation":
				return [
					{
						"name": "VCON-001",
						"consulting_practitioner_name": "",
						"consulting_practitioner": "doctor@example.com",
					}
				]
			if doctype == "User":
				return [{"name": "doctor@example.com", "full_name": "Dr Ada"}]
			return []

		with (
			patch.object(service_revenue, "_existing_doctype", return_value=True),
			patch.object(service_revenue.frappe, "get_meta", return_value=Meta()),
			patch.object(service_revenue.frappe, "get_all", side_effect=get_all),
		):
			mapping = service_revenue._consultation_practitioners(
				[{"consultation_reference": "VCON-001"}]
			)

		self.assertEqual(mapping["VCON-001"]["label"], "Dr Ada")
		self.assertEqual(mapping["VCON-001"]["user"], "doctor@example.com")

	def test_mixed_invoice_reconciles_and_separates_consultation_from_treatment(self):
		invoice = {
			"sales_invoice": "SINV-001",
			"grand_total": 1500,
			"paid_amount": 900,
			"outstanding_amount": 600,
			"service_source": "Consultation",
		}
		items = [
			{
				"item_code": "CONSULT-ITEM",
				"item_name": "Consultation",
				"description": "Consultation Fee",
				"qty": 1,
				"rate": 500,
				"net_amount": 500,
			},
			{
				"item_code": "TREATMENT-ITEM",
				"item_name": "Treatment",
				"description": "Treatment",
				"qty": 1,
				"rate": 1000,
				"net_amount": 1000,
			},
		]

		rows = service_revenue._allocate_invoice(
			invoice,
			items,
			{"CONSULT-ITEM": "Consultation Service", "TREATMENT-ITEM": "Treatment"},
			"Dr Ada",
			"doctor@example.com",
		)

		self.assertEqual([row["service_category"] for row in rows], ["Consultation Service", "Treatment"])
		self.assertAlmostEqual(sum(row["revenue_amount"] for row in rows), 1500)
		self.assertAlmostEqual(sum(row["paid_amount"] for row in rows), 900)
		self.assertAlmostEqual(sum(row["outstanding_amount"] for row in rows), 600)


if __name__ == "__main__":
	unittest.main()
