from __future__ import annotations

from contextlib import ExitStack
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from vetedge.services import hospitalisation


def activity(**values):
	defaults = {
		"name": "ACT-001",
		"idx": 1,
		"activity_type": "Medication",
		"activity_datetime": "2026-06-20 09:00:00",
		"stock_affecting": 1,
		"stock_status": "Pending",
		"item": "ITEM-STOCK",
		"qty": 2,
		"uom": "Nos",
		"billing_status": "Pending Charge",
	}
	defaults.update(values)
	return frappe._dict(defaults)


def hospitalisation_doc(**values):
	defaults = {
		"doctype": "Veterinary Hospitalisation",
		"name": "VHOS-001",
		"status": "Under Care",
		"company": "Company A",
		"service_branch": "Main",
		"payment_gate_status": "Blocked",
		"payment_gate_message": "Still blocked",
		"sales_invoice": "SINV-001",
		"activities": [],
		"charge_items": [],
	}
	defaults.update(values)
	doc = frappe._dict(defaults)
	doc.save = Mock()
	return doc


def stock_profile(is_stock_item=True, stock_uom="Nos", has_batch_no=False):
	return SimpleNamespace(
		item_code="ITEM-STOCK",
		is_stock_item=is_stock_item,
		stock_uom=stock_uom,
		disabled=False,
		has_batch_no=has_batch_no,
		has_expiry_date=False,
		shelf_life_in_days=0,
	)


class TestHospitalisationStockPosting(TestCase):
	def test_non_stock_affecting_activity_does_not_create_stock_entry(self):
		hosp = hospitalisation_doc(activities=[activity(stock_affecting=0, stock_status="Not Applicable")])
		with stock_context(hosp) as ctx:
			result = hospitalisation.post_hospitalisation_activity_stock("VHOS-001")

		self.assertEqual(result["posted_count"], 0)
		self.assertEqual(result["skipped_count"], 1)
		self.assertEqual(ctx.created_entries, [])

	def test_stock_affecting_activity_without_item_is_blocked_safely(self):
		hosp = hospitalisation_doc(activities=[activity(item=None)])
		with stock_context(hosp) as ctx:
			result = hospitalisation.post_hospitalisation_activity_stock("VHOS-001")

		self.assertEqual(result["blocked_count"], 1)
		self.assertEqual(ctx.created_entries, [])
		self.assertIn("Item", hosp.activities[0].stock_posting_message)

	def test_stock_affecting_activity_with_zero_qty_is_blocked_safely(self):
		hosp = hospitalisation_doc(activities=[activity(qty=0)])
		with stock_context(hosp) as ctx:
			result = hospitalisation.post_hospitalisation_activity_stock("VHOS-001")

		self.assertEqual(result["blocked_count"], 1)
		self.assertEqual(ctx.created_entries, [])
		self.assertIn("greater than zero", hosp.activities[0].stock_posting_message)

	def test_stock_affecting_activity_with_non_stock_item_is_blocked_safely(self):
		hosp = hospitalisation_doc(activities=[activity()])
		with stock_context(hosp, profile=stock_profile(is_stock_item=False)) as ctx:
			result = hospitalisation.post_hospitalisation_activity_stock("VHOS-001")

		self.assertEqual(result["blocked_count"], 1)
		self.assertEqual(ctx.created_entries, [])
		self.assertIn("not a stock item", hosp.activities[0].stock_posting_message)

	def test_stock_affecting_medication_activity_creates_one_stock_entry(self):
		row = activity(activity_type="Medication")
		hosp = hospitalisation_doc(activities=[row])
		with stock_context(hosp) as ctx:
			result = hospitalisation.post_hospitalisation_activity_stock("VHOS-001")

		self.assertEqual(result["posted_count"], 1)
		self.assertEqual(len(ctx.created_entries), 1)
		self.assertEqual(ctx.created_entries[0].doctype, "Stock Entry")
		self.assertEqual(ctx.created_entries[0].purpose, "Material Issue")

	def test_stock_affecting_vaccination_activity_creates_one_stock_entry(self):
		row = activity(activity_type="Vaccination")
		hosp = hospitalisation_doc(activities=[row])
		with stock_context(hosp) as ctx:
			result = hospitalisation.post_hospitalisation_activity_stock("VHOS-001")

		self.assertEqual(result["posted_count"], 1)
		self.assertEqual(result["stock_entries"], ["STE-001"])
		self.assertEqual(len(ctx.created_entries), 1)

	def test_running_stock_posting_twice_does_not_create_duplicate_entries(self):
		hosp = hospitalisation_doc(activities=[activity()])
		with stock_context(hosp) as ctx:
			first = hospitalisation.post_hospitalisation_activity_stock("VHOS-001")
			second = hospitalisation.post_hospitalisation_activity_stock("VHOS-001")

		self.assertEqual(first["posted_count"], 1)
		self.assertEqual(second["posted_count"], 0)
		self.assertEqual(second["skipped_count"], 1)
		self.assertEqual(len(ctx.created_entries), 1)

	def test_posted_activity_gets_stock_status_and_tracking_fields(self):
		row = activity()
		hosp = hospitalisation_doc(activities=[row])
		with stock_context(hosp):
			hospitalisation.post_hospitalisation_activity_stock("VHOS-001")

		self.assertEqual(row.stock_status, "Posted")
		self.assertEqual(row.stock_entry, "STE-001")
		self.assertEqual(row.posted_stock_qty, 2)
		self.assertEqual(row.stock_posted_by, "vet@example.com")
		self.assertTrue(row.stock_posted_on)

	def test_stock_posting_does_not_change_status_or_payment_gate(self):
		hosp = hospitalisation_doc(status="Under Care", payment_gate_status="Blocked", payment_gate_message="Still blocked", activities=[activity()])
		with stock_context(hosp):
			hospitalisation.post_hospitalisation_activity_stock("VHOS-001")

		self.assertEqual(hosp.status, "Under Care")
		self.assertEqual(hosp.payment_gate_status, "Blocked")
		self.assertEqual(hosp.payment_gate_message, "Still blocked")

	def test_stock_posting_does_not_create_invoice_lines(self):
		invoice = frappe._dict(name="SINV-001", items=[])
		hosp = hospitalisation_doc(activities=[activity()])
		with stock_context(hosp, invoice=invoice):
			hospitalisation.post_hospitalisation_activity_stock("VHOS-001")

		self.assertEqual(invoice.get("items"), [])

	def test_stock_posting_does_not_change_charge_status_or_build_charge_sheet(self):
		charge = frappe._dict(source_activity="ACT-001", billing_status="Pending Invoice")
		hosp = hospitalisation_doc(activities=[activity()], charge_items=[charge])
		with stock_context(hosp):
			with patch.object(hospitalisation, "build_hospitalisation_charge_items", side_effect=AssertionError("charge sheet built")):
				hospitalisation.post_hospitalisation_activity_stock("VHOS-001")

		self.assertEqual(charge.billing_status, "Pending Invoice")

	def test_cancelled_hospitalisation_blocks_stock_posting(self):
		hosp = hospitalisation_doc(status="Cancelled", activities=[activity()])
		with stock_context(hosp) as ctx:
			self.assertRaises(frappe.ValidationError, hospitalisation.post_hospitalisation_activity_stock, "VHOS-001")

		self.assertEqual(ctx.created_entries, [])


class stock_context:
	def __init__(self, hosp, profile=None, invoice=None):
		self.hosp = hosp
		self.profile = profile or stock_profile()
		self.invoice = invoice or frappe._dict(name="SINV-001", items=[])
		self.created_entries = []
		self.stack = ExitStack()

	def __enter__(self):
		hosp = self.hosp
		created_entries = self.created_entries
		invoice = self.invoice

		def exists(doctype, name=None):
			return True

		def get_doc(doctype, name=None):
			if isinstance(doctype, dict):
				entry = frappe._dict(doctype)
				entry.name = f"STE-{len(created_entries) + 1:03d}"
				entry.insert = Mock()
				entry.submit = Mock()
				entry.set = lambda key, value: setattr(entry, key, value)
				created_entries.append(entry)
				return entry
			if doctype == "Veterinary Hospitalisation":
				return hosp
			if doctype == "Sales Invoice":
				return invoice
			return frappe._dict(name=name)

		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=exists, get_value=Mock(return_value="Stores - A")),
			get_meta=lambda doctype: SimpleNamespace(has_field=lambda fieldname: fieldname in {"enable_veterinary_hospitalisation", "branch", "veterinary_hospitalisation"}),
			get_single=lambda doctype: frappe._dict(enable_veterinary_hospitalisation=1),
			get_single_value=Mock(return_value=0),
			get_doc=get_doc,
			_dict=frappe._dict,
			session=SimpleNamespace(user="vet@example.com"),
			ValidationError=frappe.ValidationError,
			throw=Mock(side_effect=frappe.ValidationError),
		)
		self.stack.enter_context(
			patch.multiple(
				hospitalisation,
				frappe=frappe_stub,
				require_internal_user=Mock(),
				get_hospitalisation_activity_item_stock_profile=Mock(return_value=self.profile),
			)
		)
		self.stack.enter_context(patch("vetedge.services.stock.validate_warehouse_company"))
		self.stack.enter_context(patch("vetedge.services.stock.get_branch_dispensary_warehouse", return_value="Stores - A"))
		self.stack.enter_context(patch("vetedge.services.stock.validate_stock_availability"))
		self.stack.enter_context(patch("vetedge.services.stock.build_stock_entry_rows", return_value=[{"item_code": "ITEM-STOCK", "qty": 2, "s_warehouse": "Stores - A"}]))
		self.stack.enter_context(patch("vetedge.services.expiry_control.allocate_item_batches", return_value=[]))
		self.stack.enter_context(patch.object(hospitalisation, "now", return_value="2026-06-20 10:00:00"))
		return self

	def __exit__(self, exc_type, exc, tb):
		return self.stack.__exit__(exc_type, exc, tb)
