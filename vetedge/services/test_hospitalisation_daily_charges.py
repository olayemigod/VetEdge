from __future__ import annotations

from contextlib import ExitStack
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from vetedge.services import hospitalisation


def hospitalisation_doc(**values):
	defaults = {
		"doctype": "Veterinary Hospitalisation",
		"name": "VHOS-001",
		"status": "Under Care",
		"company": "Company A",
		"customer": "CUST-001",
		"service_branch": "Main",
		"care_level": "Standard",
		"admission_datetime": "2026-06-19 10:00:00",
		"discharge_datetime": None,
		"payment_gate_status": "Blocked",
		"payment_gate_message": "Still blocked",
		"charge_items": [],
		"activities": [],
	}
	defaults.update(values)
	doc = frappe._dict(defaults)
	doc.is_new = lambda: False
	doc.save = Mock()
	doc.append = lambda fieldname, row: doc.setdefault(fieldname, []).append(frappe._dict(row)) or doc[fieldname][-1]
	return doc


def settings_doc(*rows):
	return frappe._dict(enable_veterinary_hospitalisation=1, hospitalisation_daily_charge_settings=[frappe._dict(row) for row in rows])


def setting(care_level="Standard", item="ITEM-STD", uom="Nos", qty_per_day=1, enabled=1):
	return {"care_level": care_level, "item": item, "uom": uom, "qty_per_day": qty_per_day, "enabled": enabled, "description": f"{care_level} stay"}


class DailyChargeContext:
	def __init__(self, hosp, settings=None, standard_rate=1000, selling_rate=0):
		self.hosp = hosp
		self.settings = settings or settings_doc(setting())
		self.standard_rate = standard_rate
		self.selling_rate = selling_rate
		self.stack = ExitStack()

	def __enter__(self):
		hosp = self.hosp
		settings = self.settings

		def get_doc(doctype, name=None):
			if doctype == "Veterinary Hospitalisation":
				return hosp
			return frappe._dict(name=name)

		def get_value(doctype, name, fieldname=None, **kwargs):
			if doctype == "Item" and fieldname == "item_name":
				return f"Item {name}"
			if doctype == "Item" and fieldname == "stock_uom":
				return "Nos"
			if doctype == "Item" and fieldname == "standard_rate":
				return self.standard_rate
			return None

		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=Mock(return_value=True), get_value=get_value),
			get_doc=get_doc,
			get_single=lambda doctype: settings,
			get_meta=lambda doctype: SimpleNamespace(has_field=lambda fieldname: True),
			_dict=frappe._dict,
			session=SimpleNamespace(user="vet@example.com"),
			ValidationError=frappe.ValidationError,
			throw=Mock(side_effect=frappe.ValidationError),
		)
		self.stack.enter_context(patch.object(hospitalisation, "frappe", frappe_stub))
		self.stack.enter_context(patch.object(hospitalisation, "require_internal_user"))
		self.stack.enter_context(patch("vetedge.services.billing_core._get_item_selling_rate", return_value=self.selling_rate))
		return self

	def __exit__(self, exc_type, exc, tb):
		return self.stack.__exit__(exc_type, exc, tb)


class TestHospitalisationDailyCharges(TestCase):
	def test_daily_charge_generation_creates_one_charge_per_date(self):
		hosp = hospitalisation_doc()
		with DailyChargeContext(hosp, selling_rate=5000):
			result = hospitalisation.generate_hospitalisation_daily_charges("VHOS-001", from_date="2026-06-19", to_date="2026-06-21")

		self.assertEqual(result["created"], 3)
		self.assertEqual(len(hosp.charge_items), 3)
		self.assertEqual(result["total_amount"], 15000)
		self.assertTrue(all(row.charge_category == "Daily Stay" for row in hosp.charge_items))

	def test_daily_charge_generation_is_idempotent(self):
		hosp = hospitalisation_doc()
		with DailyChargeContext(hosp, selling_rate=2500):
			first = hospitalisation.generate_hospitalisation_daily_charges("VHOS-001", from_date="2026-06-19", to_date="2026-06-20")
			second = hospitalisation.generate_hospitalisation_daily_charges("VHOS-001", from_date="2026-06-19", to_date="2026-06-20")

		self.assertEqual(first["created"], 2)
		self.assertEqual(second["created"], 0)
		self.assertEqual(second["updated"], 2)
		self.assertEqual(len(hosp.charge_items), 2)

	def test_different_care_levels_produce_distinct_source_keys(self):
		hosp = hospitalisation_doc()
		settings = settings_doc(setting("Standard", "ITEM-STD"), setting("ICU", "ITEM-ICU"))
		with DailyChargeContext(hosp, settings=settings, selling_rate=1000):
			hospitalisation.generate_hospitalisation_daily_charges("VHOS-001", from_date="2026-06-19", to_date="2026-06-19", care_level="Standard")
			hospitalisation.generate_hospitalisation_daily_charges("VHOS-001", from_date="2026-06-19", to_date="2026-06-19", care_level="ICU")

		self.assertEqual(len(hosp.charge_items), 2)
		self.assertNotEqual(hosp.charge_items[0].source_key, hosp.charge_items[1].source_key)

	def test_missing_daily_charge_setting_returns_structured_message(self):
		hosp = hospitalisation_doc()
		with DailyChargeContext(hosp, settings=settings_doc()):
			result = hospitalisation.generate_hospitalisation_daily_charges("VHOS-001", from_date="2026-06-19", to_date="2026-06-19")

		self.assertEqual(result["created"], 0)
		self.assertIn("not configured", result["message"])
		self.assertEqual(hosp.charge_items, [])

	def test_price_resolves_from_selling_price_and_standard_rate_fallback(self):
		hosp = hospitalisation_doc()
		with DailyChargeContext(hosp, selling_rate=3200, standard_rate=1000):
			hospitalisation.generate_hospitalisation_daily_charges("VHOS-001", from_date="2026-06-19", to_date="2026-06-19")
		self.assertEqual(hosp.charge_items[0].rate, 3200)
		self.assertEqual(hosp.charge_items[0].pricing_source, "Selling Price")

		hosp2 = hospitalisation_doc()
		with DailyChargeContext(hosp2, selling_rate=0, standard_rate=1500):
			hospitalisation.generate_hospitalisation_daily_charges("VHOS-001", from_date="2026-06-19", to_date="2026-06-19")
		self.assertEqual(hosp2.charge_items[0].rate, 1500)
		self.assertEqual(hosp2.charge_items[0].pricing_source, "Item Standard Rate")

	def test_manual_pending_rate_is_preserved_and_invoiced_not_mutated(self):
		hosp = hospitalisation_doc()
		pending = frappe._dict(source_key="daily-stay::VHOS-001::2026-06-19::Standard::ITEM-STD", source_hash="daily-stay::VHOS-001::2026-06-19::Standard::ITEM-STD", source_activity="daily-stay::VHOS-001::2026-06-19::Standard::ITEM-STD", item="ITEM-STD", qty=1, rate=7777, amount=7777, billing_status="Pending Invoice")
		invoiced = frappe._dict(source_key="daily-stay::VHOS-001::2026-06-20::Standard::ITEM-STD", source_hash="daily-stay::VHOS-001::2026-06-20::Standard::ITEM-STD", source_activity="daily-stay::VHOS-001::2026-06-20::Standard::ITEM-STD", item="ITEM-STD", qty=1, rate=8888, amount=8888, billing_status="Invoiced")
		hosp.charge_items = [pending, invoiced]
		with DailyChargeContext(hosp, selling_rate=1000):
			hospitalisation.generate_hospitalisation_daily_charges("VHOS-001", from_date="2026-06-19", to_date="2026-06-20")
		self.assertEqual(pending.rate, 7777)
		self.assertEqual(invoiced.rate, 8888)
		self.assertEqual(len(hosp.charge_items), 2)

	def test_generate_daily_charges_has_no_status_gate_or_invoice_side_effects(self):
		hosp = hospitalisation_doc(status="Admitted", payment_gate_status="Blocked", sales_invoice=None)
		with DailyChargeContext(hosp, selling_rate=1000):
			hospitalisation.generate_hospitalisation_daily_charges("VHOS-001", from_date="2026-06-19", to_date="2026-06-19")
		self.assertEqual(hosp.status, "Admitted")
		self.assertEqual(hosp.payment_gate_status, "Blocked")
		self.assertIsNone(hosp.sales_invoice)

	def test_zero_rate_daily_charge_blocks_invoice_sync_and_summary_includes_total(self):
		hosp = hospitalisation_doc()
		with DailyChargeContext(hosp, selling_rate=0, standard_rate=0):
			hospitalisation.generate_hospitalisation_daily_charges("VHOS-001", from_date="2026-06-19", to_date="2026-06-19")
			summary = hospitalisation.get_hospitalisation_charge_summary("VHOS-001")
			with self.assertRaises(frappe.ValidationError):
				hospitalisation.validate_hospitalisation_charge_prices(hosp)
		self.assertEqual(summary["missing_price_count"], 1)
		self.assertEqual(summary["total_charge_amount"], 0)
