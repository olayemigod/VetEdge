from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.dispensary import (
	DISPENSARY_CONFIRMED,
	DISPENSARY_PENDING,
	build_default_dispensed_items,
	confirm_dispensary_issue,
	get_dispensed_item_preview,
	get_consultation_ready_status,
	planned_treatment_requires_dispensary,
	sync_consultation_from_stock_entry,
)
from vetedge.services.stock import get_branch_dispensary_warehouse


class TestDispensaryFlow(TestCase):
	def test_planned_stock_item_requires_dispensary(self):
		row = frappe._dict(item="MED-001", treatment_type=None)

		with (
			patch("vetedge.services.dispensary.get_treatment_type_requires_dispensary", return_value=False),
			patch("vetedge.services.dispensary.get_treatment_item_defaults", return_value=None),
			patch(
				"vetedge.services.dispensary.get_item_stock_profile",
				return_value=SimpleNamespace(is_stock_item=True, stock_uom="Nos", has_batch_no=False, has_expiry_date=False, shelf_life_in_days=0),
			),
		):
			self.assertTrue(planned_treatment_requires_dispensary(row))

	def test_get_consultation_ready_status_returns_pending_when_confirmation_required(self):
		doc = make_consultation()

		with patch("vetedge.services.dispensary.get_dispensary_settings", return_value=SimpleNamespace(enabled=True)):
			with (
				patch("vetedge.services.dispensary.get_treatment_type_requires_dispensary", return_value=False),
				patch("vetedge.services.dispensary.get_treatment_item_defaults", return_value=None),
				patch("vetedge.services.dispensary.get_item_stock_profile", return_value=SimpleNamespace(is_stock_item=True, stock_uom="Nos", has_batch_no=False, has_expiry_date=False, shelf_life_in_days=0)),
			):
				self.assertEqual(get_consultation_ready_status(doc), "Pending Dispensary")

	def test_build_default_dispensed_items_uses_planned_quantities(self):
		doc = make_consultation()

		with (
			patch("vetedge.services.dispensary.get_treatment_type_requires_dispensary", return_value=False),
			patch("vetedge.services.dispensary.get_treatment_item_defaults", return_value=None),
			patch("vetedge.services.dispensary.get_item_stock_profile", return_value=SimpleNamespace(is_stock_item=True, stock_uom="Nos", has_batch_no=False, has_expiry_date=False, shelf_life_in_days=0)),
		):
			rows = build_default_dispensed_items(doc)

		self.assertEqual(rows[0]["planned_qty"], 2)
		self.assertEqual(rows[0]["dispensed_qty"], 2)

	def test_confirm_dispensary_issue_posts_stock_for_stock_items(self):
		doc = make_consultation()

		with (
			patch("vetedge.services.dispensary.require_internal_user"),
			patch("vetedge.services.dispensary.can_dispense"),
			patch("vetedge.services.dispensary.frappe.get_doc", return_value=doc),
			patch("vetedge.services.dispensary.frappe.session", SimpleNamespace(user="dispensary@example.com")),
			patch("vetedge.services.dispensary.get_dispensary_settings", return_value=SimpleNamespace(enabled=True)),
			patch("vetedge.services.dispensary.get_treatment_type_requires_dispensary", return_value=False),
			patch("vetedge.services.dispensary.get_treatment_item_defaults", return_value=None),
			patch("vetedge.services.dispensary.get_item_stock_profile", return_value=SimpleNamespace(is_stock_item=True, stock_uom="Nos", has_batch_no=True, has_expiry_date=True, shelf_life_in_days=30)),
			patch("vetedge.services.dispensary.get_branch_dispensary_warehouse", return_value="Main Stores"),
			patch("vetedge.services.dispensary.now_datetime", return_value="2026-04-22 10:00:00"),
			patch(
				"vetedge.services.dispensary.allocate_item_batches",
				return_value=[SimpleNamespace(batch_no="BATCH-001", qty=2, expiry_date="2026-04-30", warehouse="Main Stores")],
			),
			patch("vetedge.services.dispensary.validate_stock_item_expiry_configuration"),
			patch("vetedge.services.dispensary.validate_stock_availability"),
			patch("vetedge.services.dispensary.create_material_issue_stock_entry", return_value="STE-0001") as create_stock,
			patch("vetedge.services.dispensary.emit_notification_event"),
		):
			result = confirm_dispensary_issue("VCON-001")

		self.assertEqual(result["stock_entry"], "STE-0001")
		self.assertEqual(doc.status, "Ready for Treatment")
		self.assertEqual(doc.dispensary_status, DISPENSARY_CONFIRMED)
		self.assertEqual(doc.dispensed_treatments[0].stock_posted, 1)
		self.assertEqual(doc.dispensed_treatments[0].selected_batch, "BATCH-001")
		self.assertEqual(doc.dispensed_treatments[0].batch_allocation_summary, "BATCH-001: 2.0")
		self.assertEqual(doc.dispensed_treatments[0].stock_entry_reference, "STE-0001")
		create_stock.assert_called_once()

	def test_confirm_dispensary_issue_does_not_post_stock_for_non_stock_items(self):
		doc = make_consultation()

		with (
			patch("vetedge.services.dispensary.require_internal_user"),
			patch("vetedge.services.dispensary.can_dispense"),
			patch("vetedge.services.dispensary.frappe.get_doc", return_value=doc),
			patch("vetedge.services.dispensary.frappe.session", SimpleNamespace(user="dispensary@example.com")),
			patch("vetedge.services.dispensary.get_dispensary_settings", return_value=SimpleNamespace(enabled=True)),
			patch("vetedge.services.dispensary.get_treatment_type_requires_dispensary", return_value=True),
			patch("vetedge.services.dispensary.get_treatment_item_defaults", return_value=None),
			patch("vetedge.services.dispensary.get_item_stock_profile", return_value=SimpleNamespace(is_stock_item=False, stock_uom="Nos", has_batch_no=False, has_expiry_date=False, shelf_life_in_days=0)),
			patch("vetedge.services.dispensary.get_branch_dispensary_warehouse", return_value="Main Stores"),
			patch("vetedge.services.dispensary.now_datetime", return_value="2026-04-22 10:00:00"),
			patch("vetedge.services.dispensary.create_material_issue_stock_entry") as create_stock,
			patch("vetedge.services.dispensary.emit_notification_event"),
		):
			result = confirm_dispensary_issue("VCON-001")

		self.assertIsNone(result["stock_entry"])
		self.assertEqual(doc.dispensed_treatments[0].stock_posted, 0)
		create_stock.assert_not_called()

	def test_duplicate_confirmation_is_blocked(self):
		doc = make_consultation()
		doc.dispensary_status = DISPENSARY_CONFIRMED

		with (
			patch("vetedge.services.dispensary.require_internal_user"),
			patch("vetedge.services.dispensary.can_dispense"),
			patch("vetedge.services.dispensary.frappe.get_doc", return_value=doc),
			patch("vetedge.services.dispensary.frappe.session", SimpleNamespace(user="dispensary@example.com")),
			patch("vetedge.services.dispensary.get_dispensary_settings", return_value=SimpleNamespace(enabled=True)),
			patch("vetedge.services.dispensary.get_treatment_type_requires_dispensary", return_value=False),
			patch("vetedge.services.dispensary.get_treatment_item_defaults", return_value=None),
			patch("vetedge.services.dispensary.get_item_stock_profile", return_value=SimpleNamespace(is_stock_item=True, stock_uom="Nos", has_batch_no=False, has_expiry_date=False, shelf_life_in_days=0)),
			patch("vetedge.services.dispensary.frappe.throw", side_effect=frappe.ValidationError),
		):
			self.assertRaises(frappe.ValidationError, confirm_dispensary_issue, "VCON-001")

	def test_completed_consultation_preserves_submitted_dispensary_stock_reference(self):
		doc = make_consultation()
		doc.status = "Completed"
		doc.dispensary_status = DISPENSARY_CONFIRMED
		doc.dispensary_stock_entry = "STE-0001"
		doc.set(
			"dispensed_treatments",
			[
				frappe._dict(
					item="MED-001",
					dispensed_qty=2,
					stock_posted=1,
					stock_entry_reference="STE-0001",
					selected_batch="BATCH-001",
				)
			],
		)

		with (
			patch("vetedge.services.dispensary.require_internal_user"),
			patch("vetedge.services.dispensary.can_dispense"),
			patch("vetedge.services.dispensary.frappe.get_doc", return_value=doc),
			patch("vetedge.services.dispensary.frappe.session", SimpleNamespace(user="dispensary@example.com")),
			patch("vetedge.services.dispensary.get_dispensary_settings", return_value=SimpleNamespace(enabled=True)),
			patch("vetedge.services.dispensary.create_material_issue_stock_entry") as create_stock,
			patch("vetedge.services.dispensary.frappe.throw", side_effect=frappe.ValidationError),
		):
			self.assertRaises(frappe.ValidationError, confirm_dispensary_issue, "VCON-001")

		self.assertEqual(doc.status, "Completed")
		self.assertEqual(doc.dispensary_status, DISPENSARY_CONFIRMED)
		self.assertEqual(doc.dispensary_stock_entry, "STE-0001")
		self.assertEqual(doc.dispensed_treatments[0].stock_entry_reference, "STE-0001")
		self.assertEqual(doc.dispensed_treatments[0].stock_posted, 1)
		self.assertEqual(doc.dispensed_treatments[0].selected_batch, "BATCH-001")
		create_stock.assert_not_called()

	def test_insufficient_stock_blocks_confirmation(self):
		doc = make_consultation()

		with (
			patch("vetedge.services.dispensary.require_internal_user"),
			patch("vetedge.services.dispensary.can_dispense"),
			patch("vetedge.services.dispensary.frappe.get_doc", return_value=doc),
			patch("vetedge.services.dispensary.frappe.session", SimpleNamespace(user="dispensary@example.com")),
			patch("vetedge.services.dispensary.get_dispensary_settings", return_value=SimpleNamespace(enabled=True)),
			patch("vetedge.services.dispensary.get_treatment_type_requires_dispensary", return_value=False),
			patch("vetedge.services.dispensary.get_treatment_item_defaults", return_value=None),
			patch("vetedge.services.dispensary.get_item_stock_profile", return_value=SimpleNamespace(is_stock_item=True, stock_uom="Nos", has_batch_no=False, has_expiry_date=False, shelf_life_in_days=0)),
			patch("vetedge.services.dispensary.get_branch_dispensary_warehouse", return_value="Main Stores"),
			patch("vetedge.services.dispensary.validate_stock_item_expiry_configuration"),
			patch("vetedge.services.dispensary.validate_stock_availability", side_effect=frappe.ValidationError),
			patch("vetedge.services.dispensary.emit_notification_event") as emit,
		):
			self.assertRaises(frappe.ValidationError, confirm_dispensary_issue, "VCON-001")

		self.assertEqual(emit.call_args.args[0], "dispensary_stock_issue_failed")

	def test_expired_manual_batch_is_blocked(self):
		doc = make_consultation()

		with (
			patch("vetedge.services.dispensary.require_internal_user"),
			patch("vetedge.services.dispensary.can_dispense"),
			patch("vetedge.services.dispensary.frappe.get_doc", return_value=doc),
			patch("vetedge.services.dispensary.frappe.session", SimpleNamespace(user="dispensary@example.com")),
			patch("vetedge.services.dispensary.get_dispensary_settings", return_value=SimpleNamespace(enabled=True)),
			patch("vetedge.services.dispensary.get_treatment_type_requires_dispensary", return_value=False),
			patch("vetedge.services.dispensary.get_treatment_item_defaults", return_value=None),
			patch("vetedge.services.dispensary.get_item_stock_profile", return_value=SimpleNamespace(is_stock_item=True, stock_uom="Nos", has_batch_no=True, has_expiry_date=True, shelf_life_in_days=30)),
			patch("vetedge.services.dispensary.get_branch_dispensary_warehouse", return_value="Main Stores"),
			patch("vetedge.services.dispensary.now_datetime", return_value="2026-04-22 10:00:00"),
			patch("vetedge.services.dispensary.validate_stock_item_expiry_configuration"),
			patch("vetedge.services.dispensary.allocate_item_batches", side_effect=frappe.ValidationError("expired")),
			patch("vetedge.services.dispensary.emit_notification_event") as emit,
		):
			self.assertRaises(
				frappe.ValidationError,
				confirm_dispensary_issue,
				"VCON-001",
				[{"planned_treatment_row": "ROW-1", "item": "MED-001", "dispensed_qty": 2, "selected_batch": "BATCH-OLD"}],
			)

		self.assertEqual(emit.call_args.args[0], "dispensary_expired_stock_blocked")

	def test_expiry_sensitive_item_without_batch_setup_is_blocked(self):
		doc = make_consultation()

		with (
			patch("vetedge.services.dispensary.require_internal_user"),
			patch("vetedge.services.dispensary.can_dispense"),
			patch("vetedge.services.dispensary.frappe.get_doc", return_value=doc),
			patch("vetedge.services.dispensary.frappe.session", SimpleNamespace(user="dispensary@example.com")),
			patch("vetedge.services.dispensary.get_dispensary_settings", return_value=SimpleNamespace(enabled=True)),
			patch("vetedge.services.dispensary.get_treatment_type_requires_dispensary", return_value=False),
			patch("vetedge.services.dispensary.get_treatment_item_defaults", return_value=None),
			patch("vetedge.services.dispensary.get_item_stock_profile", return_value=SimpleNamespace(is_stock_item=True, stock_uom="Nos", has_batch_no=False, has_expiry_date=False, shelf_life_in_days=30)),
			patch("vetedge.services.dispensary.get_branch_dispensary_warehouse", return_value="Main Stores"),
			patch("vetedge.services.dispensary.now_datetime", return_value="2026-04-22 10:00:00"),
			patch("vetedge.services.dispensary.emit_notification_event") as emit,
		):
			self.assertRaises(frappe.ValidationError, confirm_dispensary_issue, "VCON-001")

		self.assertEqual(emit.call_args.args[0], "dispensary_expired_stock_blocked")

	def test_branch_warehouse_resolution_prefers_vetedge_mapping(self):
		frappe_stub = make_frappe_stub(
			get_meta=lambda doctype: SimpleNamespace(has_field=lambda fieldname: fieldname == "vetedge_dispensary_warehouse"),
			get_value=lambda doctype, name, fields=None, as_dict=False: frappe._dict(vetedge_dispensary_warehouse="Main Stores")
			if doctype == "Branch"
			else "Test Company",
		)

		with patch("vetedge.services.stock.frappe", frappe_stub):
			self.assertEqual(get_branch_dispensary_warehouse("Main", company="Test Company", required=True), "Main Stores")

	def test_sync_consultation_from_cancelled_stock_entry_reopens_dispensary(self):
		doc = make_consultation()
		doc.status = "Ready for Treatment"
		doc.dispensary_status = DISPENSARY_CONFIRMED
		doc.dispensary_stock_entry = "STE-0001"
		doc.set("dispensed_treatments", [frappe._dict(stock_posted=1)])
		stock_entry = frappe._dict(docstatus=2, vetedge_consultation="VCON-001", name="STE-0001")

		with (
			patch("vetedge.services.dispensary.frappe.get_meta", return_value=SimpleNamespace(has_field=lambda fieldname: fieldname == "vetedge_consultation")),
			patch("vetedge.services.dispensary.frappe.get_doc", return_value=doc),
			patch("vetedge.services.dispensary.consultation_requires_dispensary", return_value=True),
		):
			sync_consultation_from_stock_entry(stock_entry)

		self.assertEqual(doc.status, "Pending Dispensary")
		self.assertEqual(doc.dispensary_status, DISPENSARY_PENDING)
		self.assertEqual(doc.dispensed_treatments[0].stock_posted, 0)

	def test_get_dispensed_item_preview_returns_default_rows(self):
		doc = make_consultation()

		with (
			patch("vetedge.services.dispensary.require_internal_user"),
			patch("vetedge.services.dispensary.can_dispense"),
			patch("vetedge.services.dispensary.frappe.get_doc", return_value=doc),
			patch("vetedge.services.dispensary.frappe.session", SimpleNamespace(user="dispensary@example.com")),
			patch("vetedge.services.dispensary.get_treatment_type_requires_dispensary", return_value=False),
			patch("vetedge.services.dispensary.get_treatment_item_defaults", return_value=None),
			patch("vetedge.services.dispensary.get_item_stock_profile", return_value=SimpleNamespace(is_stock_item=True, stock_uom="Nos", has_batch_no=False, has_expiry_date=False, shelf_life_in_days=0)),
		):
			result = get_dispensed_item_preview("VCON-001")

		self.assertEqual(result["consultation"], "VCON-001")
		self.assertEqual(result["items"][0]["item"], "MED-001")


class FakeConsultation(frappe._dict):
	def append(self, fieldname, value):
		child = frappe._dict(value)
		self.setdefault(fieldname, [])
		self[fieldname].append(child)
		return child

	def set(self, key, value):
		self[key] = value

	def save(self, ignore_permissions=False):
		self.saved = True
		return self


def make_consultation():
	return FakeConsultation(
		doctype="Veterinary Consultation",
		name="VCON-001",
		status="Pending Dispensary",
		service_branch="Main",
		company="Test Company",
		payment_status="Unpaid",
		dispensary_status=DISPENSARY_PENDING,
		dispensed_treatments=[],
		planned_treatments=[
			frappe._dict(
				name="ROW-1",
				item="MED-001",
				qty=2,
				uom="Nos",
				treatment_type="Medication",
				notes="Issue from dispensary",
			)
		],
	)


def make_frappe_stub(get_meta=None, get_value=None):
	return SimpleNamespace(
		db=SimpleNamespace(
			exists=lambda *args, **kwargs: True,
			get_value=get_value or (lambda *args, **kwargs: None),
		),
		get_meta=get_meta or (lambda *args, **kwargs: SimpleNamespace(has_field=lambda fieldname: False)),
		throw=lambda message, exc=None: (_ for _ in ()).throw((exc or frappe.ValidationError)()),
		ValidationError=frappe.ValidationError,
	)
