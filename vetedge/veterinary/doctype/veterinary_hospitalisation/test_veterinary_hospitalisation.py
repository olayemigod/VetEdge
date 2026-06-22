from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase


APP_ROOT = Path("/home/olayemigod/frappe-bench/apps/vetedge/vetedge")
SETTINGS_JSON = APP_ROOT / "veterinary/doctype/veterinary_settings/veterinary_settings.json"
HOSPITALISATION_JSON = APP_ROOT / "veterinary/doctype/veterinary_hospitalisation/veterinary_hospitalisation.json"
ACTIVITY_JSON = APP_ROOT / "veterinary/doctype/veterinary_hospitalisation_activity/veterinary_hospitalisation_activity.json"
CHARGE_ITEM_JSON = APP_ROOT / "veterinary/doctype/veterinary_hospitalisation_charge_item/veterinary_hospitalisation_charge_item.json"


def load_json(path: Path) -> dict:
	return json.loads(path.read_text())


def fields_by_name(metadata: dict) -> dict[str, dict]:
	return {field["fieldname"]: field for field in metadata["fields"]}


class TestVeterinaryHospitalisationStructure(TestCase):
	def test_veterinary_settings_contains_hospitalisation_payment_gate(self):
		settings = load_json(SETTINGS_JSON)
		fields = fields_by_name(settings)

		self.assertIn("enable_veterinary_hospitalisation", fields)
		self.assertIn("hospitalisation_payment_gate", fields)
		self.assertIn("hospitalisation_payment_gate", settings["field_order"])

	def test_hospitalisation_payment_gate_defaults_to_partial_payment_gate(self):
		fields = fields_by_name(load_json(SETTINGS_JSON))

		self.assertEqual(fields["hospitalisation_payment_gate"]["default"], "Partial Payment Gate")
		self.assertEqual(
			fields["hospitalisation_payment_gate"]["options"],
			"Full Payment Required\nPartial Payment Gate\nNo Payment Gate",
		)

	def test_veterinary_hospitalisation_activity_doctype_exists(self):
		activity = load_json(ACTIVITY_JSON)

		self.assertEqual(activity["name"], "Veterinary Hospitalisation Activity")
		self.assertEqual(activity["istable"], 1)
		fields = fields_by_name(activity)
		self.assertIn("Vaccination", fields["activity_type"]["options"].splitlines())
		self.assertFalse(fields["item"].get("reqd"))

	def test_veterinary_hospitalisation_charge_item_doctype_exists(self):
		charge_item = load_json(CHARGE_ITEM_JSON)

		self.assertEqual(charge_item["name"], "Veterinary Hospitalisation Charge Item")
		self.assertEqual(charge_item["istable"], 1)
		fields = fields_by_name(charge_item)
		self.assertTrue(fields["item"].get("reqd"))
		self.assertEqual(fields["billing_status"]["options"], "Pending Invoice\nInvoiced\nCancelled")

	def test_hospitalisation_has_optional_charge_items_table(self):
		fields = fields_by_name(load_json(HOSPITALISATION_JSON))

		self.assertIn("charge_items", fields)
		self.assertEqual(fields["charge_items"]["fieldtype"], "Table")
		self.assertEqual(fields["charge_items"]["options"], "Veterinary Hospitalisation Charge Item")
		self.assertFalse(fields["charge_items"].get("reqd"))

	def test_hospitalisation_has_optional_activities_table(self):
		fields = fields_by_name(load_json(HOSPITALISATION_JSON))

		self.assertIn("activities", fields)
		self.assertEqual(fields["activities"]["fieldtype"], "Table")
		self.assertEqual(fields["activities"]["options"], "Veterinary Hospitalisation Activity")
		self.assertFalse(fields["activities"].get("reqd"))

	def test_hospitalisation_can_be_created_without_care_location(self):
		fields = fields_by_name(load_json(HOSPITALISATION_JSON))

		self.assertFalse(fields["care_location_type"].get("reqd"))
		self.assertFalse(fields["care_location"].get("reqd"))
		self.assertEqual(fields["care_location_type"]["default"], "Not Assigned")
		self.assertEqual(fields["care_location"]["options"], "Veterinary Care Location")

	def test_required_fields_work(self):
		fields = fields_by_name(load_json(HOSPITALISATION_JSON))
		required_fields = {
			fieldname
			for fieldname, field in fields.items()
			if field.get("reqd")
		}

		self.assertEqual(
			required_fields,
			{
				"naming_series",
				"patient",
				"customer",
				"status",
				"admission_datetime",
				"service_branch",
				"attending_veterinarian",
				"admission_reason",
			},
		)

	def test_sales_invoice_is_optional_until_admission_action(self):
		fields = fields_by_name(load_json(HOSPITALISATION_JSON))

		self.assertFalse(fields["sales_invoice"].get("reqd"))

	def test_status_options_exist(self):
		fields = fields_by_name(load_json(HOSPITALISATION_JSON))

		self.assertEqual(
			fields["status"]["options"].splitlines(),
			[
				"Draft",
				"Admitted",
				"Under Care",
				"Ready for Discharge",
				"Discharged",
				"Cancelled",
			],
		)
