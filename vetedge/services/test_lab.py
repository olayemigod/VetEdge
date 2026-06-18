from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from vetedge.services.lab import (
	create_lab_order_invoice,
	create_lab_order_from_consultation,
	get_consultation_lab_billing_items,
	get_lab_history,
	validate_lab_order,
)


class TestLabWorkflow(TestCase):
	def test_consultation_lab_order_action_uses_popup_not_route_after_create(self):
		script_path = Path(__file__).resolve().parents[1] / "veterinary/doctype/veterinary_consultation/veterinary_consultation.js"
		script = script_path.read_text()

		self.assertIn("open_lab_order_dialog_safely(frm)", script)
		self.assertIn("show_lab_order_summary_dialog(frm, response.message.name)", script)
		self.assertNotIn('frappe.set_route("Form", "Veterinary Lab Order", response.message.name)', script)

	def test_create_lab_order_invoice_creates_invoice_when_none_exists(self):
		order = make_lab_order()
		created_invoice = make_sales_invoice("SINV-001", docstatus=0)
		set_values = []

		with lab_invoice_context(order, created_invoice, set_values):
			result = create_lab_order_invoice("VLAB-001")

		self.assertEqual(result["invoice"], "SINV-001")
		self.assertTrue(result["created"])
		self.assertEqual(set_values[0], ("Veterinary Lab Order", "VLAB-001", "linked_invoice", "SINV-001"))
		created_invoice.insert.assert_called_once()

	def test_create_lab_order_invoice_updates_existing_draft_invoice_without_duplicate(self):
		order = make_lab_order(linked_invoice="SINV-001")
		draft_invoice = make_sales_invoice("SINV-001", docstatus=0)
		set_values = []

		with lab_invoice_context(order, draft_invoice, set_values):
			result = create_lab_order_invoice("VLAB-001")

		self.assertEqual(result["invoice"], "SINV-001")
		self.assertFalse(result["created"])
		draft_invoice.save.assert_called_once()
		draft_invoice.insert.assert_not_called()
		self.assertEqual(len(draft_invoice["items"]), 1)

	def test_create_lab_order_invoice_does_not_mutate_submitted_invoice(self):
		order = make_lab_order(linked_invoice="SINV-001")
		submitted_invoice = make_sales_invoice("SINV-001", docstatus=1)
		set_values = []

		with lab_invoice_context(order, submitted_invoice, set_values):
			result = create_lab_order_invoice("VLAB-001")

		self.assertEqual(result["invoice"], "SINV-001")
		self.assertTrue(result["submitted"])
		submitted_invoice.save.assert_not_called()
		submitted_invoice.insert.assert_not_called()
		self.assertEqual(set_values, [])

	def test_create_lab_order_invoice_replaces_cancelled_invoice_with_new_invoice(self):
		order = make_lab_order(linked_invoice="SINV-CAN")
		cancelled_invoice = make_sales_invoice("SINV-CAN", docstatus=2)
		new_invoice = make_sales_invoice("SINV-NEW", docstatus=0)
		set_values = []

		with lab_invoice_context(order, cancelled_invoice, set_values, created_invoice=new_invoice):
			result = create_lab_order_invoice("VLAB-001")

		self.assertEqual(result["invoice"], "SINV-NEW")
		self.assertTrue(result["created"])
		new_invoice.insert.assert_called_once()
		self.assertEqual(set_values[0], ("Veterinary Lab Order", "VLAB-001", "linked_invoice", "SINV-NEW"))

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


def make_lab_order(linked_invoice=None):
	order = frappe._dict(
		doctype="Veterinary Lab Order",
		name="VLAB-001",
		patient="VP-001",
		primary_owner="CUST-001",
		consultation=None,
		service_branch="Main",
		linked_invoice=linked_invoice,
		lab_tests=[
			frappe._dict(
				lab_test_template="CBC",
				billing_item="LAB-CBC",
				get=lambda key, default=None: {"lab_test_template": "CBC", "billing_item": "LAB-CBC"}.get(key, default),
			)
		],
	)
	order.get = lambda key, default=None: order[key] if key in order else default
	return order


def make_sales_invoice(name, docstatus=0):
	invoice = frappe._dict(
		doctype="Sales Invoice",
		name=name,
		docstatus=docstatus,
		customer="CUST-001",
		grand_total=1000,
		items=[],
	)
	invoice.insert = Mock(return_value=invoice)
	invoice.save = Mock(return_value=invoice)
	invoice.set = lambda fieldname, value: invoice.__setitem__(fieldname, value)
	invoice.append = lambda fieldname, value: invoice[fieldname].append(value)
	invoice.get = lambda key, default=None: invoice[key] if key in invoice else default
	return invoice


class lab_invoice_context:
	def __init__(self, order, linked_invoice, set_values, created_invoice=None):
		self.order = order
		self.linked_invoice = linked_invoice
		self.created_invoice = created_invoice or linked_invoice
		self.set_values = set_values
		self.stack = None

	def __enter__(self):
		from contextlib import ExitStack

		self.stack = ExitStack()

		def get_doc(arg1, arg2=None):
			if arg1 == "Veterinary Lab Order":
				return self.order
			if arg1 == "Sales Invoice":
				return self.linked_invoice
			if isinstance(arg1, dict):
				invoice = self.created_invoice or make_sales_invoice("SINV-001")
				invoice.update(arg1)
				return invoice
			raise AssertionError(f"Unexpected get_doc call: {arg1} {arg2}")

		frappe_stub = SimpleNamespace(
			get_doc=get_doc,
			db=SimpleNamespace(
				exists=lambda doctype, name=None: doctype == "Sales Invoice" and name == self.linked_invoice.name,
				get_value=lambda *args, **kwargs: 1000,
				set_value=lambda doctype, name, field, value, **kwargs: self.set_values.append((doctype, name, field, value)),
			),
			get_meta=lambda doctype: SimpleNamespace(has_field=lambda fieldname: True),
			utils=SimpleNamespace(nowdate=lambda: "2026-06-18"),
			throw=lambda message, exc=None: (_ for _ in ()).throw((exc or frappe.ValidationError)(message)),
			ValidationError=frappe.ValidationError,
		)
		self.stack.enter_context(patch("vetedge.services.lab.frappe", frappe_stub))
		self.stack.enter_context(patch("vetedge.services.lab.require_internal_user"))
		self.stack.enter_context(patch("vetedge.services.lab.can_access_lab_order"))
		self.stack.enter_context(patch("vetedge.services.registration_billing.get_billing_cost_center", return_value="Main - CC"))
		self.stack.enter_context(patch("vetedge.services.registration_billing.get_default_company", return_value="Test Company"))
		self.stack.enter_context(patch("vetedge.services.billing.validate_sales_item"))
		self.stack.enter_context(
			patch(
				"vetedge.services.billing.frappe",
				SimpleNamespace(
					db=SimpleNamespace(get_value=lambda *args, **kwargs: frappe._dict(stock_uom="Nos", standard_rate=1000)),
					throw=lambda message, exc=None: (_ for _ in ()).throw((exc or frappe.ValidationError)(message)),
					ValidationError=frappe.ValidationError,
				),
			)
		)
		self.stack.enter_context(patch("vetedge.services.lab.emit_notification_event"))
		return self

	def __exit__(self, exc_type, exc, tb):
		self.stack.close()
		return False
