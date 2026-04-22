from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from vetedge.services.billing import (
	ConsultationBillingSettings,
	create_consultation_invoice,
	get_invoice_payment_status,
	update_single_consultation_payment_status,
	validate_consultation_invoice_request,
)


class TestConsultationBilling(TestCase):
	def test_disabled_consultation_billing_blocks_invoice_creation(self):
		consultation = frappe._dict(
			name="VCON-001",
			status="In Progress",
			patient="VP-001",
			primary_owner="CUST-001",
			service_branch="Main",
			linked_invoice=None,
		)
		settings = ConsultationBillingSettings(False, None, False, False, False, True)

		with patch("vetedge.services.billing.frappe.throw", side_effect=frappe.ValidationError):
			self.assertRaises(
				frappe.ValidationError,
				validate_consultation_invoice_request,
				consultation,
				settings,
			)

	def test_create_consultation_invoice_includes_consultation_and_treatments(self):
		consultation = make_consultation()
		invoice = make_invoice()
		settings = ConsultationBillingSettings(True, "CONSULT-ITEM", False, True, True, True)
		set_values = []

		with patched_invoice_context(consultation, invoice, settings, set_values) as get_doc:
			result = create_consultation_invoice("VCON-001")

		invoice_data = get_doc.call_args_list[1].args[0]
		self.assertEqual(result["invoice"], "SINV-001")
		self.assertEqual(invoice_data["customer"], "CUST-001")
		self.assertEqual(invoice_data["items"][0]["item_code"], "CONSULT-ITEM")
		self.assertEqual(invoice_data["items"][1]["item_code"], "XRAY")
		self.assertEqual(invoice_data["items"][1]["qty"], 2)
		self.assertEqual(invoice_data["items"][1]["rate"], 500)
		self.assertEqual(invoice_data["items"][1]["cost_center"], "Main - CC")
		self.assertEqual(invoice.cost_center, "Main - CC")
		self.assertEqual(invoice.branch, "Main")
		self.assertEqual(set_values[0][2]["linked_invoice"], "SINV-001")
		self.assertEqual(set_values[0][2]["status"], "Awaiting Payment")

	def test_duplicate_active_invoice_is_prevented(self):
		consultation = make_consultation(linked_invoice="SINV-001")
		settings = ConsultationBillingSettings(True, "CONSULT-ITEM", False, False, False, True)

		with (
			patch("vetedge.services.billing.is_active_sales_invoice", return_value=True),
			patch("vetedge.services.billing.frappe.throw", side_effect=frappe.ValidationError),
		):
			self.assertRaises(
				frappe.ValidationError,
				validate_consultation_invoice_request,
				consultation,
				settings,
			)

	def test_paid_invoice_status_sets_consultation_ready_for_treatment(self):
		consultation = frappe._dict(name="VCON-001", status="Awaiting Payment", payment_status="Unpaid")
		invoice = frappe._dict(
			name="SINV-001",
			docstatus=1,
			outstanding_amount=0,
			grand_total=1000,
			customer="CUST-001",
		)
		set_values = []

		with (
			patch("vetedge.services.billing.frappe", make_frappe_stub(set_values=set_values, get_value=lambda *args, **kwargs: "Main")),
			patch("vetedge.services.billing.emit_notification_event") as emit,
		):
			update_single_consultation_payment_status(consultation, invoice)

		self.assertEqual(set_values[0][2]["payment_status"], "Paid")
		self.assertEqual(set_values[0][2]["status"], "Ready for Treatment")
		self.assertEqual(emit.call_args_list[0].args[0], "payment_received")

	def test_partly_paid_invoice_status(self):
		invoice = frappe._dict(docstatus=1, outstanding_amount=250, grand_total=1000)

		self.assertEqual(get_invoice_payment_status(invoice), "Partly Paid")


def make_consultation(linked_invoice=None):
	return frappe._dict(
		doctype="Veterinary Consultation",
		name="VCON-001",
		status="In Progress",
		patient="VP-001",
		primary_owner="CUST-001",
		service_branch="Main",
		company="Test Company",
		linked_invoice=linked_invoice,
		planned_treatments=[
			frappe._dict(item="XRAY", qty=2, uom="Nos", rate=500),
		],
	)


def make_invoice():
	invoice = frappe._dict(name="SINV-001", customer="CUST-001")
	invoice.insert = lambda ignore_permissions=False: invoice
	return invoice


class patched_invoice_context:
	def __init__(self, consultation, invoice, settings, set_values):
		self.consultation = consultation
		self.invoice = invoice
		self.settings = settings
		self.set_values = set_values
		self.stack = None

	def __enter__(self):
		from contextlib import ExitStack

		self.stack = ExitStack()
		get_doc = Mock(side_effect=self.get_doc)
		frappe_stub = make_frappe_stub(set_values=self.set_values, get_doc=get_doc, get_value=get_value)
		self.stack.enter_context(patch("vetedge.services.billing.frappe", frappe_stub))
		self.stack.enter_context(patch("vetedge.services.billing.get_consultation_billing_settings", return_value=self.settings))
		self.stack.enter_context(patch("vetedge.services.billing.get_billing_cost_center", return_value="Main - CC"))
		self.stack.enter_context(patch("vetedge.services.billing.nowdate", return_value="2026-04-20"))
		self.stack.enter_context(patch("vetedge.services.billing.emit_notification_event", return_value={"queued": False}))
		return get_doc

	def __exit__(self, exc_type, exc, tb):
		return self.stack.__exit__(exc_type, exc, tb)

	def get_doc(self, *args, **kwargs):
		if args == ("Veterinary Consultation", "VCON-001"):
			return self.consultation
		if args and isinstance(args[0], dict):
			return self.invoice
		raise AssertionError(f"Unexpected get_doc args: {args}")


def get_value(doctype, name, fields=None, as_dict=False):
	if doctype == "Item":
		return frappe._dict(
			disabled=0,
			is_sales_item=1,
			is_stock_item=0,
			stock_uom="Nos",
			standard_rate=1000,
		)
	return None


def make_frappe_stub(set_values=None, get_doc=None, get_value=None):
	set_values = set_values if set_values is not None else []
	get_doc = get_doc or (lambda *args, **kwargs: None)
	get_value = get_value or (lambda *args, **kwargs: None)

	def throw(*args, **kwargs):
		exc = args[1] if len(args) > 1 else kwargs.get("exc")
		if isinstance(exc, type) and issubclass(exc, Exception):
			raise exc()
		raise frappe.ValidationError()

	return SimpleNamespace(
		db=SimpleNamespace(
			get_value=get_value,
			set_value=lambda *args, **kwargs: set_values.append(args),
		),
		get_doc=get_doc,
		get_roles=lambda *args, **kwargs: ["VetEdge Front Desk"],
		get_meta=lambda *args, **kwargs: SimpleNamespace(has_field=lambda field: True),
		session=SimpleNamespace(user="staff@example.com"),
		throw=throw,
		ValidationError=frappe.ValidationError,
		PermissionError=frappe.PermissionError,
	)
