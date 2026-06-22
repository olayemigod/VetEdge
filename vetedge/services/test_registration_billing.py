from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.registration_billing import (
	AWAITING_PAYMENT_STATUS,
	PAID_STATUS,
	REGISTERED_STATUS,
	RegistrationBillingRule,
	create_manual_registration_invoice,
	create_registration_invoice,
	get_billing_cost_center,
	get_registration_rule,
	handle_patient_registration_insert,
	is_first_consultation_for_patient,
	is_invoice_paid,
	update_registration_status_from_invoice,
	update_registration_status_from_payment_entry,
	update_patient_registration_payment_status,
	validate_registration_payment_before_first_consultation,
	validate_registration_item,
	validate_patient_registration,
)


class TestRegistrationBilling(TestCase):
	def setUp(self):
		self.patcher = patch("vetedge.services.registration_billing.use_billing_core_for_registration", return_value=False)
		self.patcher.start()

	def tearDown(self):
		self.patcher.stop()

	def test_registration_without_billing_sets_registered(self):
		patient = frappe._dict(name="VET-PAT-001", default_branch="Main")
		rule = RegistrationBillingRule(False, "Main", None, 0, False, False)

		with (
			patch("vetedge.services.registration_billing.get_registration_rule", return_value=rule),
			patch("vetedge.services.registration_billing.set_patient_registration_fields") as set_fields,
		):
			handle_patient_registration_insert(patient)

		set_fields.assert_called_once_with(patient.name, registration_status=REGISTERED_STATUS)

	def test_registration_with_billing_requires_item(self):
		patient = frappe._dict(name="VET-PAT-001", default_branch="Main", primary_owner="CUST-001")
		rule = RegistrationBillingRule(True, "Main", None, 0, True, False)

		with (
			patch("vetedge.services.registration_billing.get_registration_rule", return_value=rule),
			patch("vetedge.services.registration_billing.frappe.throw", side_effect=frappe.ValidationError),
		):
			self.assertRaises(frappe.ValidationError, validate_patient_registration, patient)

	def test_registration_with_billing_requires_branch(self):
		patient = frappe._dict(name="VET-PAT-001", default_branch=None, primary_owner="CUST-001")
		rule = RegistrationBillingRule(True, None, "REG-ITEM", 0, True, False)

		with (
			patch("vetedge.services.registration_billing.get_registration_rule", return_value=rule),
			patch("vetedge.services.registration_billing.frappe.throw", side_effect=frappe.ValidationError),
		):
			self.assertRaises(frappe.ValidationError, validate_patient_registration, patient)

	def test_registration_with_billing_creates_invoice(self):
		patient = frappe._dict(
			name="VET-PAT-001",
			default_branch="Main",
			primary_owner="CUST-001",
			registration_invoice=None,
		)
		rule = RegistrationBillingRule(True, "Main", "REG-ITEM", 1500, True, False)
		invoice = SimpleNamespace(name="SINV-001")

		with (
			patch("vetedge.services.registration_billing.get_registration_rule", return_value=rule),
			patch("vetedge.services.registration_billing.create_registration_invoice", return_value=invoice) as create_invoice,
			patch("vetedge.services.registration_billing.set_patient_registration_fields") as set_fields,
			patch("vetedge.services.registration_billing.get_existing_registration_invoice", return_value=None),
		):
			handle_patient_registration_insert(patient)

		create_invoice.assert_called_once_with(patient, rule)
		set_fields.assert_called_once_with(
			patient.name,
			registration_invoice=invoice.name,
			registration_status=AWAITING_PAYMENT_STATUS,
			registration_billed=1,
			registration_fee_amount=rule.registration_fee,
		)

	def test_duplicate_invoice_is_not_created(self):
		patient = frappe._dict(
			name="VET-PAT-001",
			default_branch="Main",
			primary_owner="CUST-001",
			registration_invoice="SINV-001",
		)
		rule = RegistrationBillingRule(True, "Main", "REG-ITEM", 1500, True, False)

		with (
			patch("vetedge.services.registration_billing.get_registration_rule", return_value=rule),
			patch("vetedge.services.registration_billing.create_registration_invoice") as create_invoice,
			patch("vetedge.services.registration_billing.update_patient_registration_payment_status") as update_status,
		):
			handle_patient_registration_insert(patient)

		create_invoice.assert_not_called()
		update_status.assert_called_once_with(patient.name, patient.registration_invoice)

	def test_manual_registration_invoice_is_created_later(self):
		patient = frappe._dict(
			name="VET-PAT-001",
			default_branch="Main",
			primary_owner="CUST-001",
			registration_invoice=None,
			registration_status=REGISTERED_STATUS,
		)
		rule = RegistrationBillingRule(True, "Main", "REG-ITEM", 1500, False, False)
		invoice = SimpleNamespace(name="SINV-NEW")

		with (
			patch("vetedge.services.registration_billing.require_internal_user"),
			patch("vetedge.services.registration_billing.can_access_patient"),
			patch("vetedge.services.registration_billing.frappe.session", SimpleNamespace(user="staff@example.com")),
			patch("vetedge.services.registration_billing.frappe.get_doc", return_value=patient),
			patch("vetedge.services.registration_billing.get_registration_rule", return_value=rule),
			patch("vetedge.services.registration_billing.get_active_registration_invoice_name", return_value=None),
			patch("vetedge.services.registration_billing.create_registration_invoice", return_value=invoice),
			patch("vetedge.services.registration_billing.set_patient_registration_fields") as set_fields,
		):
			result = create_manual_registration_invoice(patient.name)

		self.assertEqual(
			result,
			{
				"patient": patient.name,
				"invoice": invoice.name,
				"created": True,
				"status": AWAITING_PAYMENT_STATUS,
			},
		)
		set_fields.assert_called_once_with(
			patient.name,
			registration_invoice=invoice.name,
			registration_status=AWAITING_PAYMENT_STATUS,
			registration_billed=1,
			registration_fee_amount=rule.registration_fee,
		)

	def test_manual_registration_invoice_reuses_existing_active_invoice(self):
		patient = frappe._dict(
			name="VET-PAT-001",
			default_branch="Main",
			primary_owner="CUST-001",
			registration_invoice="SINV-001",
			registration_status=REGISTERED_STATUS,
		)
		rule = RegistrationBillingRule(True, "Main", "REG-ITEM", 1500, False, False)

		with (
			patch("vetedge.services.registration_billing.require_internal_user"),
			patch("vetedge.services.registration_billing.can_access_patient"),
			patch("vetedge.services.registration_billing.frappe.session", SimpleNamespace(user="staff@example.com")),
			patch("vetedge.services.registration_billing.frappe.get_doc", return_value=patient),
			patch("vetedge.services.registration_billing.get_registration_rule", return_value=rule),
			patch("vetedge.services.registration_billing.get_active_registration_invoice_name", return_value="SINV-001"),
			patch("vetedge.services.registration_billing.update_patient_registration_payment_status") as update_status,
			patch("vetedge.services.registration_billing.create_registration_invoice") as create_invoice,
			patch("vetedge.services.registration_billing.frappe.db.get_value", return_value=AWAITING_PAYMENT_STATUS),
		):
			result = create_manual_registration_invoice(patient.name)

		self.assertEqual(
			result,
			{
				"patient": patient.name,
				"invoice": "SINV-001",
				"created": False,
				"status": AWAITING_PAYMENT_STATUS,
			},
		)
		update_status.assert_called_once_with(patient.name, "SINV-001")
		create_invoice.assert_not_called()

	def test_paid_invoice_is_detected(self):
		invoice = SimpleNamespace(docstatus=1, status="Paid", outstanding_amount=0)

		self.assertTrue(is_invoice_paid(invoice))

	def test_draft_invoice_is_not_paid(self):
		invoice = SimpleNamespace(docstatus=0, status="Paid", outstanding_amount=0)

		self.assertFalse(is_invoice_paid(invoice))

	def test_registration_status_moves_to_awaiting_payment_for_unpaid_invoice(self):
		invoice = SimpleNamespace(name="SINV-001", docstatus=1, status="Unpaid", outstanding_amount=500)

		with patch("vetedge.services.registration_billing.set_patient_registration_fields") as set_fields:
			update_patient_registration_payment_status("VET-PAT-001", invoice)

		set_fields.assert_called_once_with(
			"VET-PAT-001",
			registration_invoice=invoice.name,
			registration_status=AWAITING_PAYMENT_STATUS,
			registration_billed=1,
		)

	def test_cancelled_registration_invoice_resets_patient_to_registered(self):
		invoice = SimpleNamespace(name="SINV-001", docstatus=2, status="Cancelled", outstanding_amount=1500)

		with patch("vetedge.services.registration_billing.set_patient_registration_fields") as set_fields:
			update_patient_registration_payment_status("VET-PAT-001", invoice)

		set_fields.assert_called_once_with(
			"VET-PAT-001",
			registration_invoice=None,
			registration_status=REGISTERED_STATUS,
			registration_billed=0,
		)

	def test_invoice_hook_updates_each_linked_patient(self):
		invoice = SimpleNamespace(name="SINV-001")

		with (
			patch("vetedge.services.registration_billing.frappe.get_all", return_value=["VP-001", "VP-002"]),
			patch("vetedge.services.registration_billing.update_patient_registration_payment_status") as update_status,
		):
			update_registration_status_from_invoice(invoice)

		update_status.assert_any_call("VP-001", invoice)
		update_status.assert_any_call("VP-002", invoice)
		self.assertEqual(update_status.call_count, 2)

	def test_payment_entry_hook_updates_registration_status_for_referenced_invoice(self):
		payment_entry = frappe._dict(
			references=[
				frappe._dict(reference_doctype="Sales Invoice", reference_name="SINV-001"),
				frappe._dict(reference_doctype="Journal Entry", reference_name="JV-001"),
			]
		)
		invoice = SimpleNamespace(name="SINV-001")

		with (
			patch("vetedge.services.registration_billing.frappe.get_doc", return_value=invoice),
			patch("vetedge.services.registration_billing.update_registration_status_from_invoice") as update_from_invoice,
		):
			update_registration_status_from_payment_entry(payment_entry)

		update_from_invoice.assert_called_once_with(invoice, None)

	def test_branch_rule_overrides_global_registration_values(self):
		settings = frappe._dict(
			enable_registration_billing=1,
			default_registration_item="GLOBAL-ITEM",
			default_registration_fee=100,
			auto_create_invoice_on_registration=0,
			require_payment_before_first_consultation=0,
			enforce_cost_center_on_billing=1,
			branch_registration_rules=[
				frappe._dict(
					branch="Main",
					registration_item="BRANCH-ITEM",
					registration_fee=250,
					auto_create_invoice_on_registration=1,
					require_payment_before_first_consultation=1,
					is_active=1,
				)
			],
		)

		with patch("vetedge.services.registration_billing.get_registration_settings", return_value=settings):
			rule = get_registration_rule("Main")

		self.assertEqual(rule.registration_item, "BRANCH-ITEM")
		self.assertEqual(rule.registration_fee, 250)
		self.assertTrue(rule.auto_create_invoice)
		self.assertTrue(rule.require_payment_before_first_consultation)
		self.assertTrue(rule.enforce_cost_center)

	def test_global_registration_values_are_used_without_branch_rule(self):
		settings = frappe._dict(
			enable_registration_billing=1,
			default_registration_item="GLOBAL-ITEM",
			default_registration_fee=100,
			auto_create_invoice_on_registration=1,
			require_payment_before_first_consultation=0,
			enforce_cost_center_on_billing=1,
			branch_registration_rules=[],
		)

		with patch("vetedge.services.registration_billing.get_registration_settings", return_value=settings):
			rule = get_registration_rule("Main")

		self.assertEqual(rule.registration_item, "GLOBAL-ITEM")
		self.assertEqual(rule.registration_fee, 100)
		self.assertTrue(rule.auto_create_invoice)

	def test_branch_rule_can_disable_global_auto_create_invoice(self):
		settings = frappe._dict(
			enable_registration_billing=1,
			default_registration_item="GLOBAL-ITEM",
			default_registration_fee=100,
			auto_create_invoice_on_registration=1,
			require_payment_before_first_consultation=0,
			enforce_cost_center_on_billing=1,
			branch_registration_rules=[
				frappe._dict(
					branch="Main",
					registration_item="BRANCH-ITEM",
					registration_fee=250,
					auto_create_invoice_on_registration=0,
					require_payment_before_first_consultation=0,
					is_active=1,
				)
			],
		)

		with patch("vetedge.services.registration_billing.get_registration_settings", return_value=settings):
			rule = get_registration_rule("Main")

		self.assertFalse(rule.auto_create_invoice)

	def test_registration_payment_gate_blocks_unpaid_first_consultation(self):
		patient_doc = frappe._dict(
			name="VP-001",
			default_branch="Main",
			registration_status=AWAITING_PAYMENT_STATUS,
			registration_invoice="SINV-001",
		)
		rule = RegistrationBillingRule(True, "Main", "REG-ITEM", 100, True, True)

		with (
			patch("vetedge.services.registration_billing.frappe.db.get_value", return_value=patient_doc),
			patch("vetedge.services.registration_billing.get_registration_rule", return_value=rule),
			patch("vetedge.services.registration_billing.is_first_consultation_for_patient", return_value=True),
			patch("vetedge.services.registration_billing.frappe.throw", side_effect=frappe.ValidationError),
		):
			self.assertRaises(
				frappe.ValidationError,
				validate_registration_payment_before_first_consultation,
				"VP-001",
			)

	def test_registration_payment_gate_allows_paid_first_consultation(self):
		patient_doc = frappe._dict(
			name="VP-001",
			default_branch="Main",
			registration_status="Registration Paid",
			registration_invoice="SINV-001",
		)
		rule = RegistrationBillingRule(True, "Main", "REG-ITEM", 100, True, True)

		with (
			patch("vetedge.services.registration_billing.frappe.db.get_value", return_value=patient_doc),
			patch("vetedge.services.registration_billing.get_registration_rule", return_value=rule),
			patch("vetedge.services.registration_billing.is_first_consultation_for_patient", return_value=True),
			patch("vetedge.services.registration_billing.get_active_registration_invoice_name", return_value="SINV-001"),
			patch(
				"vetedge.services.registration_billing.frappe.get_doc",
				return_value=frappe._dict(name="SINV-001", docstatus=1, status="Paid", outstanding_amount=0),
			),
			patch("vetedge.services.registration_billing.update_patient_registration_payment_status"),
		):
			validate_registration_payment_before_first_consultation("VP-001")

	def test_registration_payment_gate_blocks_missing_invoice_even_if_status_is_paid(self):
		patient_doc = frappe._dict(
			name="VP-001",
			default_branch="Main",
			registration_status=PAID_STATUS,
			registration_invoice=None,
		)
		rule = RegistrationBillingRule(True, "Main", "REG-ITEM", 100, True, True)

		with (
			patch("vetedge.services.registration_billing.frappe.db.get_value", return_value=patient_doc),
			patch("vetedge.services.registration_billing.get_registration_rule", return_value=rule),
			patch("vetedge.services.registration_billing.is_first_consultation_for_patient", return_value=True),
			patch("vetedge.services.registration_billing.get_active_registration_invoice_name", return_value=None),
			patch("vetedge.services.registration_billing.frappe.throw", side_effect=frappe.ValidationError),
		):
			self.assertRaises(
				frappe.ValidationError,
				validate_registration_payment_before_first_consultation,
				"VP-001",
			)

	def test_registration_payment_gate_uses_invoice_truth_before_paid_status(self):
		patient_doc = frappe._dict(
			name="VP-001",
			default_branch="Main",
			registration_status=PAID_STATUS,
			registration_invoice="SINV-001",
		)
		rule = RegistrationBillingRule(True, "Main", "REG-ITEM", 100, True, True)
		invoice = frappe._dict(name="SINV-001", docstatus=1, status="Unpaid", outstanding_amount=100)

		with (
			patch("vetedge.services.registration_billing.frappe.db.get_value", return_value=patient_doc),
			patch("vetedge.services.registration_billing.get_registration_rule", return_value=rule),
			patch("vetedge.services.registration_billing.is_first_consultation_for_patient", return_value=True),
			patch("vetedge.services.registration_billing.get_active_registration_invoice_name", return_value="SINV-001"),
			patch("vetedge.services.registration_billing.frappe.get_doc", return_value=invoice),
			patch("vetedge.services.registration_billing.update_patient_registration_payment_status"),
			patch("vetedge.services.registration_billing.frappe.throw", side_effect=frappe.ValidationError),
		):
			self.assertRaises(
				frappe.ValidationError,
				validate_registration_payment_before_first_consultation,
				"VP-001",
			)

	def test_first_consultation_check_ignores_cancelled_consultations(self):
		with patch("vetedge.services.registration_billing.frappe.get_all", return_value=[]):
			self.assertTrue(is_first_consultation_for_patient("VP-001"))

	def test_branch_with_cost_center_creates_invoice_with_cost_center(self):
		patient = frappe._dict(default_branch="Main", primary_owner="CUST-001")
		rule = RegistrationBillingRule(True, "Main", "REG-ITEM", 1500, True, False, True)
		invoice = frappe._dict(name="SINV-001")
		invoice.insert = lambda ignore_permissions=False: invoice

		with (
			patch("vetedge.services.registration_billing.get_default_company", return_value="Test Company"),
			patch("vetedge.services.registration_billing.get_billing_cost_center", return_value="Main - CC"),
			patch("vetedge.services.registration_billing.nowdate", return_value="2026-04-18"),
			patch("vetedge.services.registration_billing.frappe.get_doc", return_value=invoice) as get_doc,
			patch("vetedge.services.registration_billing.frappe.get_meta") as get_meta,
		):
			get_meta.return_value.has_field.return_value = True
			create_registration_invoice(patient, rule)

		invoice_data = get_doc.call_args.args[0]
		self.assertEqual(invoice_data["items"][0]["cost_center"], "Main - CC")
		self.assertEqual(invoice.cost_center, "Main - CC")
		self.assertEqual(invoice.branch, "Main")

	def test_branch_without_cost_center_errors_when_required(self):
		with (
			patch("vetedge.services.registration_billing.get_branch_cost_center", return_value=None),
			patch("vetedge.services.registration_billing.frappe.throw", side_effect=frappe.ValidationError),
		):
			self.assertRaises(frappe.ValidationError, get_billing_cost_center, "Main", True)

	def test_registration_item_must_be_non_stock_sales_item(self):
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(
				get_value=lambda *args, **kwargs: frappe._dict(
					disabled=0,
					is_sales_item=1,
					is_stock_item=1,
				)
			),
			throw=lambda *args, **kwargs: (_ for _ in ()).throw(frappe.ValidationError()),
			ValidationError=frappe.ValidationError,
		)

		with (
			patch("vetedge.services.registration_billing.frappe", frappe_stub),
		):
			self.assertRaises(frappe.ValidationError, validate_registration_item, "REG-ITEM", "Registration Item")
