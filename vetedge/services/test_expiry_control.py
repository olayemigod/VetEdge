from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.expiry_control import (
	allocate_item_batches,
	get_available_valid_batches,
	get_expiry_control_settings,
)


class TestExpiryControl(TestCase):
	def test_checkbox_settings_are_coerced_correctly(self):
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=lambda *args, **kwargs: True),
			get_meta=lambda *args, **kwargs: frappe._dict(has_field=lambda fieldname: True),
			get_single=lambda *args, **kwargs: frappe._dict(
				enforce_strict_expiry_control="0",
				batch_selection_policy="FEFO",
				block_manual_expired_batch_override="1",
			),
		)
		with patch("vetedge.services.expiry_control.frappe", frappe_stub):
			settings = get_expiry_control_settings()

		self.assertFalse(settings.enforce_strict_expiry_control)
		self.assertTrue(settings.block_manual_expired_batch_override)

	def test_get_available_valid_batches_respects_warehouse_order(self):
		with (
			patch("vetedge.services.expiry_control.frappe.get_single_value", return_value="Expiry"),
			patch("vetedge.services.expiry_control.safe_now_datetime", return_value="2026-04-22 10:00:00"),
			patch(
				"erpnext.stock.doctype.batch.batch.get_available_batches",
				return_value={"BATCH-EARLY": 2, "BATCH-LATE": 5},
			),
			patch(
				"vetedge.services.expiry_control.frappe.get_all",
				return_value=[
					frappe._dict(name="BATCH-EARLY", expiry_date="2026-04-25"),
					frappe._dict(name="BATCH-LATE", expiry_date="2026-04-30"),
				],
			),
		):
			rows = get_available_valid_batches("MED-001", "Main Stores")

		self.assertEqual([row.batch_no for row in rows], ["BATCH-EARLY", "BATCH-LATE"])
		self.assertTrue(all(row.warehouse == "Main Stores" for row in rows))

	def test_allocate_item_batches_prefers_earliest_valid_expiry(self):
		with patch(
			"vetedge.services.expiry_control.get_available_valid_batches",
			return_value=[
				frappe._dict(batch_no="BATCH-EARLY", qty=2, expiry_date="2026-04-25", warehouse="Main Stores"),
				frappe._dict(batch_no="BATCH-LATE", qty=5, expiry_date="2026-04-30", warehouse="Main Stores"),
			],
		):
			allocations = allocate_item_batches("MED-001", "Main Stores", 3)

		self.assertEqual(
			[(allocation.batch_no, allocation.qty) for allocation in allocations],
			[("BATCH-EARLY", 2), ("BATCH-LATE", 1)],
		)

	def test_allocate_item_batches_blocks_insufficient_non_expired_stock(self):
		with patch(
			"vetedge.services.expiry_control.get_available_valid_batches",
			return_value=[
				frappe._dict(batch_no="BATCH-ONE", qty=1, expiry_date="2026-04-25", warehouse="Main Stores"),
			],
		):
			with self.assertRaises(frappe.ValidationError):
				allocate_item_batches("MED-001", "Main Stores", 2)

	def test_allocate_item_batches_validates_manual_batch(self):
		with patch(
			"vetedge.services.expiry_control.get_available_valid_batches",
			return_value=[
				frappe._dict(batch_no="BATCH-GOOD", qty=3, expiry_date="2026-04-25", warehouse="Main Stores"),
			],
		):
			allocations = allocate_item_batches(
				"MED-001",
				"Main Stores",
				2,
				manual_batch_no="BATCH-GOOD",
			)

		self.assertEqual(len(allocations), 1)
		self.assertEqual(allocations[0].batch_no, "BATCH-GOOD")

	def test_allocate_item_batches_blocks_expired_manual_batch(self):
		with (
			patch("vetedge.services.expiry_control.get_available_valid_batches", return_value=[]),
			patch(
				"vetedge.services.expiry_control.get_batch_record",
				return_value=frappe._dict(
					name="BATCH-OLD",
					item="MED-001",
					expiry_date="2020-01-01",
					disabled=0,
				),
			),
		):
			with self.assertRaises(frappe.ValidationError):
				allocate_item_batches("MED-001", "Main Stores", 1, manual_batch_no="BATCH-OLD")
