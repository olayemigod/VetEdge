from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from vetedge.services.billing import (
	ConsultationBillingSettings,
	consultation_requires_invoice_before_progress,
	create_consultation_invoice,
	get_invoice_access_summary,
	get_invoice_payment_status,
	update_single_consultation_payment_status,
	validate_consultation_invoice_before_progress,
	validate_consultation_payment_before_treatment,
	validate_consultation_invoice_request,
)


class TestConsultationBilling(TestCase):
	def setUp(self):
		self.patcher = patch("vetedge.services.billing.use_billing_core_for_source", return_value=False)
		self.patcher.start()

	def tearDown(self):
		self.patcher.stop()

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

	def test_existing_draft_invoice_is_allowed_for_update(self):
		consultation = make_consultation(linked_invoice="SINV-001")
		settings = ConsultationBillingSettings(True, "CONSULT-ITEM", False, False, False, True)

		validate_consultation_invoice_request(consultation, settings)

	def test_paid_invoice_status_sets_consultation_ready_for_treatment(self):
		consultation = frappe._dict(name="VCON-001", status="Awaiting Payment", payment_status="Unpaid")
		consultation_doc = make_consultation()
		invoice = frappe._dict(
			name="SINV-001",
			docstatus=1,
			outstanding_amount=0,
			grand_total=1000,
			customer="CUST-001",
		)
		set_values = []

		with (
			patch(
				"vetedge.services.billing.frappe",
				make_frappe_stub(
					set_values=set_values,
					get_doc=lambda doctype, name: consultation_doc,
					get_value=lambda *args, **kwargs: "Main",
				),
			),
			patch("vetedge.services.billing.get_consultation_ready_status", return_value="Ready for Treatment"),
			patch("vetedge.services.billing.emit_notification_event") as emit,
		):
			update_single_consultation_payment_status(consultation, invoice)

		self.assertEqual(set_values[0][2]["payment_status"], "Paid")
		self.assertEqual(set_values[0][2]["status"], "Ready for Treatment")
		self.assertEqual(emit.call_args_list[0].args[0], "payment_received")

	def test_partly_paid_invoice_status(self):
		invoice = frappe._dict(docstatus=1, outstanding_amount=250, grand_total=1000)

		self.assertEqual(get_invoice_payment_status(invoice), "Partly Paid")

	def test_create_consultation_invoice_sets_pending_dispensary_when_required(self):
		consultation = make_consultation()
		invoice = make_invoice()
		settings = ConsultationBillingSettings(True, "CONSULT-ITEM", False, False, True, True)
		set_values = []

		with (
			patched_invoice_context(consultation, invoice, settings, set_values),
			patch("vetedge.services.billing.get_consultation_ready_status", return_value="Pending Dispensary"),
		):
			result = create_consultation_invoice("VCON-001")

		self.assertEqual(result["status"], "Pending Dispensary")
		self.assertEqual(set_values[0][2]["status"], "Pending Dispensary")

	def test_create_consultation_invoice_from_draft_moves_to_in_progress_not_awaiting_payment(self):
		consultation = make_consultation(status="Draft")
		invoice = make_invoice()
		settings = ConsultationBillingSettings(True, "CONSULT-ITEM", False, True, True, True)
		set_values = []

		with patched_invoice_context(consultation, invoice, settings, set_values):
			result = create_consultation_invoice("VCON-001")

		self.assertEqual(result["status"], "In Progress")
		self.assertEqual(set_values[0][2]["status"], "In Progress")

	def test_create_consultation_invoice_can_preserve_consultation_status(self):
		consultation = make_consultation()
		invoice = make_invoice()
		settings = ConsultationBillingSettings(True, "CONSULT-ITEM", False, False, True, True)
		set_values = []

		with (
			patched_invoice_context(consultation, invoice, settings, set_values),
			patch("vetedge.services.billing.get_consultation_ready_status", return_value="Ready for Treatment"),
		):
			result = create_consultation_invoice("VCON-001", update_status=0)

		self.assertEqual(result["invoice"], "SINV-001")
		self.assertEqual(result["status"], "In Progress")
		self.assertNotIn("status", set_values[0][2])
		self.assertEqual(consultation.status, "In Progress")

	def test_paid_invoice_status_sets_consultation_pending_dispensary_when_required(self):
		consultation = frappe._dict(name="VCON-001", status="Awaiting Payment", payment_status="Unpaid")
		consultation_doc = make_consultation()
		invoice = frappe._dict(
			name="SINV-001",
			docstatus=1,
			outstanding_amount=0,
			grand_total=1000,
			customer="CUST-001",
		)
		set_values = []

		with (
			patch(
				"vetedge.services.billing.frappe",
				make_frappe_stub(
					set_values=set_values,
					get_doc=lambda doctype, name: consultation_doc,
					get_value=lambda *args, **kwargs: "Main",
				),
			),
			patch("vetedge.services.billing.get_consultation_ready_status", return_value="Pending Dispensary"),
			patch("vetedge.services.billing.emit_notification_event") as emit,
		):
			update_single_consultation_payment_status(consultation, invoice)

		self.assertEqual(set_values[0][2]["status"], "Pending Dispensary")
		self.assertEqual(emit.call_args_list[1].args[0], "consultation_sent_to_dispensary")

	def test_no_payment_gate_submitted_unpaid_invoice_sets_consultation_pending_dispensary_when_required(self):
		consultation = frappe._dict(name="VCON-001", status="Awaiting Payment", payment_status="Unpaid")
		consultation_doc = make_consultation()
		invoice = frappe._dict(
			name="SINV-001",
			docstatus=1,
			outstanding_amount=1000,
			grand_total=1000,
			customer="CUST-001",
		)
		set_values = []

		with (
			patch(
				"vetedge.services.billing.frappe",
				make_frappe_stub(
					set_values=set_values,
					get_doc=lambda doctype, name: consultation_doc,
					get_value=lambda *args, **kwargs: "Main",
				),
			),
			patch("vetedge.services.payment_gate.get_consultation_payment_gate", return_value="No Payment Gate"),
			patch("vetedge.services.billing.get_consultation_ready_status", return_value="Pending Dispensary"),
			patch("vetedge.services.billing.emit_notification_event") as emit,
		):
			update_single_consultation_payment_status(consultation, invoice)

		self.assertEqual(set_values[0][2]["payment_status"], "Unpaid")
		self.assertEqual(set_values[0][2]["status"], "Pending Dispensary")
		emit.assert_not_called()

	def test_no_payment_gate_submitted_unpaid_invoice_sets_consultation_ready_for_treatment_without_dispensary(self):
		consultation = frappe._dict(name="VCON-001", status="Awaiting Payment", payment_status="Unpaid")
		consultation_doc = make_consultation()
		invoice = frappe._dict(
			name="SINV-001",
			docstatus=1,
			outstanding_amount=1000,
			grand_total=1000,
			customer="CUST-001",
		)
		set_values = []

		with (
			patch(
				"vetedge.services.billing.frappe",
				make_frappe_stub(
					set_values=set_values,
					get_doc=lambda doctype, name: consultation_doc,
					get_value=lambda *args, **kwargs: "Main",
				),
			),
			patch("vetedge.services.payment_gate.get_consultation_payment_gate", return_value="No Payment Gate"),
			patch("vetedge.services.billing.get_consultation_ready_status", return_value="Ready for Treatment"),
			patch("vetedge.services.billing.emit_notification_event") as emit,
		):
			update_single_consultation_payment_status(consultation, invoice)

		self.assertEqual(set_values[0][2]["payment_status"], "Unpaid")
		self.assertEqual(set_values[0][2]["status"], "Ready for Treatment")
		emit.assert_not_called()

	def test_no_payment_gate_submitted_unpaid_invoice_advances_in_progress_consultation(self):
		consultation = frappe._dict(name="VCON-001", status="In Progress", payment_status="Unpaid")
		consultation_doc = make_consultation(status="In Progress")
		invoice = frappe._dict(
			name="SINV-001",
			docstatus=1,
			outstanding_amount=1000,
			grand_total=1000,
			customer="CUST-001",
		)
		set_values = []

		with (
			patch(
				"vetedge.services.billing.frappe",
				make_frappe_stub(
					set_values=set_values,
					get_doc=lambda doctype, name: consultation_doc,
					get_value=lambda *args, **kwargs: "Main",
				),
			),
			patch("vetedge.services.payment_gate.get_consultation_payment_gate", return_value="No Payment Gate"),
			patch("vetedge.services.billing.get_consultation_ready_status", return_value="Ready for Treatment"),
		):
			update_single_consultation_payment_status(consultation, invoice)

		self.assertEqual(set_values[0][2]["payment_status"], "Unpaid")
		self.assertEqual(set_values[0][2]["status"], "Ready for Treatment")

	def test_full_payment_required_submitted_unpaid_invoice_does_not_advance_consultation(self):
		consultation = frappe._dict(name="VCON-001", status="Awaiting Payment", payment_status="Unpaid")
		consultation_doc = make_consultation()
		invoice = frappe._dict(
			name="SINV-001",
			docstatus=1,
			outstanding_amount=1000,
			grand_total=1000,
			customer="CUST-001",
		)
		set_values = []

		with (
			patch(
				"vetedge.services.billing.frappe",
				make_frappe_stub(
					set_values=set_values,
					get_doc=lambda doctype, name: consultation_doc,
					get_value=lambda *args, **kwargs: "Main",
				),
			),
			patch("vetedge.services.payment_gate.get_consultation_payment_gate", return_value="Full Payment Required"),
			patch("vetedge.services.billing.get_consultation_ready_status", return_value="Ready for Treatment"),
		):
			update_single_consultation_payment_status(consultation, invoice)

		self.assertEqual(set_values[0][2], {"payment_status": "Unpaid"})

	def test_partial_payment_gate_submitted_partly_paid_invoice_advances_consultation(self):
		consultation = frappe._dict(name="VCON-001", status="Awaiting Payment", payment_status="Unpaid")
		consultation_doc = make_consultation()
		invoice = frappe._dict(
			name="SINV-001",
			docstatus=1,
			outstanding_amount=750,
			grand_total=1000,
			customer="CUST-001",
		)
		set_values = []

		with (
			patch(
				"vetedge.services.billing.frappe",
				make_frappe_stub(
					set_values=set_values,
					get_doc=lambda doctype, name: consultation_doc,
					get_value=lambda *args, **kwargs: "Main",
				),
			),
			patch("vetedge.services.payment_gate.get_consultation_payment_gate", return_value="Partial Payment Gate"),
			patch("vetedge.services.payment_gate.has_valid_payment", return_value=True),
			patch("vetedge.services.billing.get_consultation_ready_status", return_value="Ready for Treatment"),
		):
			update_single_consultation_payment_status(consultation, invoice)

		self.assertEqual(set_values[0][2]["payment_status"], "Partly Paid")
		self.assertEqual(set_values[0][2]["status"], "Ready for Treatment")

	def test_partial_payment_gate_without_valid_payment_does_not_advance_consultation(self):
		consultation = frappe._dict(name="VCON-001", status="Awaiting Payment", payment_status="Unpaid")
		consultation_doc = make_consultation()
		invoice = frappe._dict(
			name="SINV-001",
			docstatus=1,
			outstanding_amount=1000,
			grand_total=1000,
			customer="CUST-001",
		)
		set_values = []

		with (
			patch(
				"vetedge.services.billing.frappe",
				make_frappe_stub(
					set_values=set_values,
					get_doc=lambda doctype, name: consultation_doc,
					get_value=lambda *args, **kwargs: "Main",
				),
			),
			patch("vetedge.services.payment_gate.get_consultation_payment_gate", return_value="Partial Payment Gate"),
			patch("vetedge.services.payment_gate.has_valid_payment", return_value=False),
			patch("vetedge.services.billing.get_consultation_ready_status", return_value="Ready for Treatment"),
		):
			update_single_consultation_payment_status(consultation, invoice)

		self.assertEqual(set_values[0][2], {"payment_status": "Unpaid"})

	def test_consultation_requires_invoice_before_progress_when_billing_enabled(self):
		consultation = make_consultation()
		settings = ConsultationBillingSettings(True, "CONSULT-ITEM", False, True, True, True)

		with patch("vetedge.services.billing.get_consultation_billing_settings", return_value=settings):
			self.assertTrue(consultation_requires_invoice_before_progress(consultation, "Ready for Treatment"))

	def test_validate_consultation_invoice_before_progress_blocks_without_invoice(self):
		consultation = make_consultation()
		settings = ConsultationBillingSettings(True, "CONSULT-ITEM", False, True, True, True)

		with (
			patch("vetedge.services.billing.get_consultation_billing_settings", return_value=settings),
			patch("vetedge.services.billing.user_has_any_role", return_value=False),
			patch(
				"vetedge.services.billing.frappe.get_doc",
				return_value=frappe._dict(docstatus=1, outstanding_amount=1000, grand_total=1000),
			),
			patch("vetedge.services.billing.frappe.throw", side_effect=frappe.ValidationError),
		):
			self.assertRaises(
				frappe.ValidationError,
				validate_consultation_invoice_before_progress,
				consultation,
				"Ready for Treatment",
			)

	def test_validate_consultation_invoice_before_progress_allows_active_invoice(self):
		consultation = make_consultation(linked_invoice="SINV-001")
		settings = ConsultationBillingSettings(True, "CONSULT-ITEM", False, True, True, True)

		with (
			patch("vetedge.services.billing.get_consultation_billing_settings", return_value=settings),
			patch("vetedge.services.billing.is_active_sales_invoice", return_value=True),
		):
			validate_consultation_invoice_before_progress(consultation, "Ready for Treatment")

	def test_validate_consultation_payment_before_treatment_blocks_unpaid_progress(self):
		consultation = make_consultation(linked_invoice="SINV-001")
		consultation.payment_status = "Unpaid"
		settings = ConsultationBillingSettings(True, "CONSULT-ITEM", False, True, True, True)

		with (
			patch("vetedge.services.billing.get_consultation_billing_settings", return_value=settings),
			patch("vetedge.services.billing.user_has_any_role", return_value=False),
			patch(
				"vetedge.services.billing.frappe.get_doc",
				return_value=frappe._dict(docstatus=1, outstanding_amount=1000, grand_total=1000),
			),
			patch("vetedge.services.billing.frappe.throw", side_effect=frappe.ValidationError),
		):
			self.assertRaises(
				frappe.ValidationError,
				validate_consultation_payment_before_treatment,
				consultation,
				"Ready for Treatment",
			)

	def test_validate_consultation_payment_before_treatment_allows_paid_progress(self):
		consultation = make_consultation(linked_invoice="SINV-001")
		consultation.payment_status = "Paid"
		settings = ConsultationBillingSettings(True, "CONSULT-ITEM", False, True, True, True)

		with patch("vetedge.services.billing.get_consultation_billing_settings", return_value=settings):
			validate_consultation_payment_before_treatment(consultation, "Ready for Treatment")

	def test_get_invoice_access_summary_uses_invoice_permission_helper(self):
		invoice_row = frappe._dict(
			name="SINV-001",
			customer="CUST-001",
			posting_date="2026-04-20",
			due_date="2026-04-20",
			status="Unpaid",
			outstanding_amount=1000,
			grand_total=1000,
			currency="NGN",
			branch="Main",
		)
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(get_value=lambda *args, **kwargs: invoice_row),
			get_doc=lambda *args, **kwargs: invoice_row,
			get_meta=lambda *args, **kwargs: SimpleNamespace(has_field=lambda field: field == "branch"),
			has_permission=lambda *args, **kwargs: True,
			session=SimpleNamespace(user="staff@example.com"),
			throw=lambda message, exc=None: (_ for _ in ()).throw((exc or frappe.ValidationError)()),
			_dict=frappe._dict,
			PermissionError=frappe.PermissionError,
		)

		with (
			patch("vetedge.services.billing.frappe", frappe_stub),
			patch("vetedge.services.billing.require_internal_user"),
			patch(
				"vetedge.services.billing.get_invoice_access_diagnostic",
				return_value={"allowed": True, "can_open_full_form": True},
			) as diagnostic,
		):
			summary = get_invoice_access_summary("SINV-001")

		diagnostic.assert_called_once_with("staff@example.com", "SINV-001")
		self.assertEqual(summary["name"], "SINV-001")
		self.assertEqual(summary["customer"], "CUST-001")
		self.assertTrue(summary["can_open_full_form"])

	def test_partial_payment_updates_consultation_and_child_rows(self):
		consultation_doc = frappe._dict(
			name="VCON-001",
			status="Awaiting Payment",
			payment_status="Unpaid",
			linked_invoice="SINV-001",
			consultation_invoices=[
				frappe._dict(sales_invoice="SINV-001", invoice_status="Unpaid")
			],
			consultation_billing_sources=[
				frappe._dict(sales_invoice="SINV-001", invoice_status="Unpaid", source_type="Treatment", source_name="PT-1")
			]
		)
		invoice = frappe._dict(
			name="SINV-001",
			docstatus=1,
			status="Partially Paid",
			outstanding_amount=250,
			grand_total=1000,
			customer="CUST-001",
			posting_date="2026-04-20",
			due_date="2026-04-20",
			currency="NGN"
		)
		set_values = []
		saved_docs = []
		consultation_doc.save = lambda *args, **kwargs: saved_docs.append(consultation_doc)

		with (
			patch(
				"vetedge.services.billing.frappe",
				make_frappe_stub(
					set_values=set_values,
					get_doc=lambda doctype, name: consultation_doc,
					get_value=lambda *args, **kwargs: "Main",
				),
			),
			patch("vetedge.services.billing.get_consultation_ready_status", return_value="Ready for Treatment"),
			patch("vetedge.services.billing.emit_notification_event") as emit,
		):
			from vetedge.services.billing import sync_consultation_invoice_reference_from_invoice
			sync_consultation_invoice_reference_from_invoice("VCON-001", invoice)

		# The parent consultation should have "Partly Paid"
		self.assertEqual(consultation_doc.payment_status, "Partly Paid")
		self.assertNotEqual(consultation_doc.payment_status, "Partially Paid")

		# The child rows should have "Partly Paid"
		self.assertEqual(consultation_doc.consultation_invoices[0].invoice_status, "Partly Paid")
		self.assertEqual(consultation_doc.consultation_billing_sources[0].invoice_status, "Partly Paid")


def make_consultation(linked_invoice=None, status="In Progress"):
	return frappe._dict(
		doctype="Veterinary Consultation",
		name="VCON-001",
		status=status,
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
		self.stack.enter_context(patch("vetedge.services.billing.get_consultation_ready_status", return_value="Ready for Treatment"))
		self.stack.enter_context(patch("vetedge.services.billing.get_billing_cost_center", return_value="Main - CC"))
		self.stack.enter_context(patch("vetedge.services.billing.nowdate", return_value="2026-04-20"))
		self.stack.enter_context(patch("vetedge.services.billing.emit_notification_event", return_value={"queued": False}))
		self.stack.enter_context(patch("vetedge.services.billing.can_access_consultation"))
		self.stack.enter_context(patch("vetedge.services.billing.can_initiate_payment"))
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
			exists=lambda *args, **kwargs: True,
		),
		get_doc=get_doc,
		get_all=lambda *args, **kwargs: [],
		get_roles=lambda *args, **kwargs: ["VetEdge Front Desk"],
		get_meta=lambda *args, **kwargs: SimpleNamespace(has_field=lambda field: True),
		session=SimpleNamespace(user="staff@example.com"),
		throw=throw,
		_dict=frappe._dict,
		ValidationError=frappe.ValidationError,
		PermissionError=frappe.PermissionError,
	)
