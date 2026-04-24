from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.lab import (
	create_lab_order_from_consultation,
	get_consultation_lab_billing_items,
	get_lab_history,
	validate_lab_order,
)


class TestLabWorkflow(TestCase):
	def test_create_lab_order_from_consultation_creates_requested_order(self):
		inserted = []
		created = frappe._dict(
			name="VLAB-2026-00001",
			status="Requested",
			insert=lambda ignore_permissions=True: inserted.append(True),
		)
		consultation_doc = frappe._dict(
			name="VCON-001",
			patient="VP-001",
			primary_owner="CUST-001",
			service_branch="Main Branch",
		)

		def get_doc(arg1, arg2=None):
			if isinstance(arg1, dict):
				created.update(arg1)
				return created
			if arg1 == "Veterinary Consultation":
				return consultation_doc
			raise AssertionError(f"Unexpected get_doc call: {arg1} {arg2}")

		frappe_stub = SimpleNamespace(
			get_doc=get_doc,
			parse_json=lambda value: value,
			_dict=frappe._dict,
			throw=lambda message, exc=None: (_ for _ in ()).throw((exc or frappe.ValidationError)(message)),
			ValidationError=frappe.ValidationError,
		)

		with (
			patch("vetedge.services.lab.frappe", frappe_stub),
			patch("vetedge.services.lab.require_internal_user"),
			patch("vetedge.services.lab.can_access_consultation"),
			patch("vetedge.services.lab.can_request_lab_tests"),
			patch("vetedge.services.lab.get_current_user", return_value="doctor@example.com"),
			patch("vetedge.services.lab.now_datetime", return_value="2026-04-23 10:00:00"),
		):
			result = create_lab_order_from_consultation(
				"VCON-001",
				[
					{"lab_test_template": "CBC", "notes": "Urgent"},
					{"lab_test_template": "UA"},
				],
				sample_notes="Collect fasting sample",
			)

		self.assertEqual(result, {"name": "VLAB-2026-00001", "status": "Requested"})
		self.assertTrue(inserted)
		self.assertEqual(created.patient, "VP-001")
		self.assertEqual(created.primary_owner, "CUST-001")
		self.assertEqual(created.consultation, "VCON-001")
		self.assertEqual(created.sample_notes, "Collect fasting sample")
		self.assertEqual(created.lab_tests[0]["lab_test_template"], "CBC")

	def test_create_lab_order_from_consultation_blocks_ready_for_treatment_consultation(self):
		consultation_doc = frappe._dict(
			name="VCON-001",
			patient="VP-001",
			primary_owner="CUST-001",
			service_branch="Main Branch",
			status="Ready for Treatment",
		)

		frappe_stub = SimpleNamespace(
			get_doc=lambda doctype, name: consultation_doc,
			parse_json=lambda value: value,
			_dict=frappe._dict,
			throw=lambda message, exc=None: (_ for _ in ()).throw((exc or frappe.ValidationError)(message)),
			ValidationError=frappe.ValidationError,
		)

		with (
			patch("vetedge.services.lab.frappe", frappe_stub),
			patch("vetedge.services.lab.require_internal_user"),
			patch("vetedge.services.lab.can_access_consultation"),
			patch("vetedge.services.lab.get_current_user", return_value="doctor@example.com"),
		):
			with self.assertRaises(frappe.ValidationError):
				create_lab_order_from_consultation(
					"VCON-001",
					[{"lab_test_template": "CBC"}],
				)

	def test_validate_lab_order_blocks_unauthorized_result_entry(self):
		doc = frappe._dict(
			doctype="Veterinary Lab Order",
			name="VLAB-001",
			patient="VP-001",
			primary_owner="CUST-001",
			consultation="VCON-001",
			service_branch="Main Branch",
			status="In Progress",
			requested_by="doctor@example.com",
			requested_on="2026-04-23 10:00:00",
			lab_tests=[
				frappe._dict(
					name="ROW-1",
					lab_test_template="CBC",
					result_value="12.3",
					result_text="",
					remarks="Stable",
					status="Result Entered",
					result_status="Entered",
					billing_item="LAB-CBC",
					get=lambda key, default=None: row_current[key] if key in row_current else default,
				)
			],
			get=lambda key, default=None: doc[key] if key in doc else default,
		)
		row_current = doc.lab_tests[0]
		previous = frappe._dict(
			status="In Progress",
			patient="VP-001",
			primary_owner="CUST-001",
			consultation="VCON-001",
			service_branch="Main Branch",
			lab_tests=[
				frappe._dict(
					name="ROW-1",
					lab_test_template="CBC",
					result_value="",
					result_text="",
					remarks="",
					status="In Progress",
					result_status="Pending",
					billing_item="LAB-CBC",
					get=lambda key, default=None: row_previous[key] if key in row_previous else default,
				)
			],
			get=lambda key, default=None: previous[key] if key in previous else default,
		)
		row_previous = previous.lab_tests[0]
		doc.get_doc_before_save = lambda: previous

		def get_value(doctype, name, fields=None, as_dict=False, **kwargs):
			if doctype == "Veterinary Patient":
				return frappe._dict(primary_owner="CUST-001", default_branch="Main Branch")
			if doctype == "Veterinary Consultation":
				return frappe._dict(patient="VP-001", primary_owner="CUST-001", service_branch="Main Branch")
			if doctype == "Veterinary Lab Test":
				return frappe._dict(
					test_name="Complete Blood Count",
					sample_type="Blood",
					linked_item="LAB-CBC",
					default_rate=5000,
					is_active=1,
				)
			raise AssertionError(f"Unexpected get_value call: {doctype} {name} {fields}")

		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(get_value=get_value),
			throw=lambda message, exc=None: (_ for _ in ()).throw((exc or frappe.ValidationError)(message)),
			ValidationError=frappe.ValidationError,
			PermissionError=frappe.PermissionError,
		)

		with (
			patch("vetedge.services.lab.frappe", frappe_stub),
			patch("vetedge.services.lab.get_current_user", return_value="frontdesk@example.com"),
			patch("vetedge.services.billing.validate_sales_item"),
			patch("vetedge.services.lab.can_access_consultation"),
			patch("vetedge.services.lab.can_access_branch_data"),
			patch("vetedge.services.lab.can_request_lab_tests"),
			patch("vetedge.services.lab.can_enter_lab_results", side_effect=frappe.PermissionError),
		):
			with self.assertRaises(frappe.PermissionError):
				validate_lab_order(doc)

	def test_lab_billing_items_include_unbilled_consultation_orders(self):
		consultation = frappe._dict(name="VCON-001")
		get_all_calls = []

		def get_all(doctype, filters=None, fields=None, order_by=None, **kwargs):
			get_all_calls.append((doctype, filters))
			if doctype == "Veterinary Lab Order":
				return [
					frappe._dict(name="VLAB-001", linked_invoice=""),
					frappe._dict(name="VLAB-002", linked_invoice="SINV-0001"),
				]
			if doctype == "Veterinary Lab Order Item":
				return [
					frappe._dict(parent="VLAB-001", lab_test_template="CBC", billing_item="LAB-CBC"),
					frappe._dict(parent="VLAB-001", lab_test_template="UA", billing_item=""),
				]
			return []

		frappe_stub = SimpleNamespace(
			get_all=get_all,
			db=SimpleNamespace(
				exists=lambda doctype, name=None: True,
				get_value=lambda doctype, name, fieldname: 4500 if name == "CBC" else 3000,
			),
		)

		with (
			patch("vetedge.services.lab.frappe", frappe_stub),
			patch("vetedge.services.billing.build_invoice_item", return_value={"item_code": "LAB-CBC", "qty": 1}) as build_item,
		):
			items, sources = get_consultation_lab_billing_items(consultation, "Main Cost Center")

		self.assertEqual(items, [{"item_code": "LAB-CBC", "qty": 1}])
		self.assertEqual(
			sources,
			[{"source_type": "Lab Order", "source_name": "VLAB-001", "sales_invoice": None, "item_code": "LAB-CBC"}],
		)
		build_item.assert_called_once_with("LAB-CBC", 1, None, 4500, "Main Cost Center")
		self.assertEqual(get_all_calls[0][0], "Veterinary Lab Order")

	def test_get_lab_history_summarizes_tests_and_results(self):
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=lambda doctype, name=None: True),
			get_list=lambda doctype, **kwargs: [
				frappe._dict(
					name="VLAB-001",
					consultation="VCON-001",
					requested_on="2026-04-18 11:00:00",
					requested_by="doctor@example.com",
					service_branch="Branch B",
					status="Reviewed",
					doctor_reviewed_by="doctor@example.com",
					doctor_reviewed_on="2026-04-18 12:00:00",
				)
			],
			get_all=lambda doctype, **kwargs: [
				frappe._dict(
					parent="VLAB-001",
					lab_test_name="CBC",
					lab_test_template="CBC",
					result_value="Normal",
					result_text="",
				),
				frappe._dict(
					parent="VLAB-001",
					lab_test_name="Urinalysis",
					lab_test_template="UA",
					result_value="",
					result_text="No abnormality detected",
				),
			],
		)

		with (
			patch("vetedge.services.lab.frappe", frappe_stub),
		):
			rows = get_lab_history("VP-001", 20, "2026-04-01", "2026-04-30")

		self.assertEqual(rows[0]["type"], "lab")
		self.assertEqual(rows[0]["tests_summary"], "CBC, Urinalysis")
		self.assertIn("CBC: Normal", rows[0]["results_summary"])
		self.assertIn("Urinalysis: No abnormality detected", rows[0]["results_summary"])

	def test_create_lab_order_invoice_blocks_consultation_linked_orders(self):
		from vetedge.services.lab import create_lab_order_invoice

		order = frappe._dict(
			name="VLAB-001",
			consultation="VCON-001",
			linked_invoice="",
			primary_owner="CUST-001",
			service_branch="Main Branch",
			get=lambda key, default=None: order[key] if key in order else default,
		)
		frappe_stub = SimpleNamespace(
			get_doc=lambda doctype, name: order,
			throw=lambda message, exc=None: (_ for _ in ()).throw((exc or frappe.ValidationError)(message)),
			ValidationError=frappe.ValidationError,
		)

		with (
			patch("vetedge.services.lab.frappe", frappe_stub),
			patch("vetedge.services.lab.require_internal_user"),
			patch("vetedge.services.lab.can_access_lab_order"),
		):
			with self.assertRaises(frappe.ValidationError):
				create_lab_order_invoice("VLAB-001")

	def test_validate_lab_order_blocks_edit_to_reviewed_result(self):
		reviewed_row = frappe._dict(
			name="ROW-1",
			lab_test_template="CBC",
			result_value="Normal",
			result_text="",
			remarks="Locked",
			status="Reviewed",
			result_status="Reviewed",
			entered_by="doctor@example.com",
			entered_on="2026-04-23 11:00:00",
			billing_item="LAB-CBC",
			get=lambda key, default=None: reviewed_row[key] if key in reviewed_row else default,
		)
		doc = frappe._dict(
			doctype="Veterinary Lab Order",
			name="VLAB-010",
			patient="VP-001",
			primary_owner="CUST-001",
			consultation="VCON-001",
			service_branch="Main Branch",
			status="Reviewed",
			requested_by="doctor@example.com",
			requested_on="2026-04-23 10:00:00",
			doctor_reviewed_by="doctor@example.com",
			doctor_reviewed_on="2026-04-23 12:00:00",
			lab_tests=[
				frappe._dict(
					reviewed_row,
					result_value="Edited Result",
					get=lambda key, default=None: current_row[key] if key in current_row else default,
				)
			],
			get=lambda key, default=None: doc[key] if key in doc else default,
		)
		current_row = doc.lab_tests[0]
		previous = frappe._dict(
			status="Reviewed",
			patient="VP-001",
			primary_owner="CUST-001",
			consultation="VCON-001",
			service_branch="Main Branch",
			lab_tests=[reviewed_row],
			get=lambda key, default=None: previous[key] if key in previous else default,
		)
		doc.get_doc_before_save = lambda: previous

		def get_value(doctype, name, fields=None, as_dict=False, **kwargs):
			if doctype == "Veterinary Patient":
				return frappe._dict(primary_owner="CUST-001", default_branch="Main Branch")
			if doctype == "Veterinary Consultation":
				return frappe._dict(patient="VP-001", primary_owner="CUST-001", service_branch="Main Branch")
			if doctype == "Veterinary Lab Test":
				return frappe._dict(
					test_name="Complete Blood Count",
					sample_type="Blood",
					linked_item="LAB-CBC",
					default_rate=5000,
					is_active=1,
				)
			if doctype == "Veterinary Patient" and fields == "patient_name":
				return "Bella"
			raise AssertionError(f"Unexpected get_value call: {doctype} {name} {fields}")

		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(get_value=get_value),
			throw=lambda message, exc=None: (_ for _ in ()).throw((exc or frappe.ValidationError)(message)),
			ValidationError=frappe.ValidationError,
			PermissionError=frappe.PermissionError,
		)

		with (
			patch("vetedge.services.lab.frappe", frappe_stub),
			patch("vetedge.services.lab.get_current_user", return_value="doctor@example.com"),
			patch("vetedge.services.billing.validate_sales_item"),
			patch("vetedge.services.lab.can_access_consultation"),
			patch("vetedge.services.lab.can_access_branch_data"),
			patch("vetedge.services.lab.can_request_lab_tests"),
		):
			with self.assertRaises(frappe.ValidationError):
				validate_lab_order(doc)
