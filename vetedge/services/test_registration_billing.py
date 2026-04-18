from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.registration_billing import (
	AWAITING_PAYMENT_STATUS,
	REGISTERED_STATUS,
	RegistrationBillingRule,
	create_registration_invoice,
	get_billing_cost_center,
	get_registration_rule,
	handle_patient_registration_insert,
	is_invoice_paid,
	validate_registration_item,
	validate_patient_registration,
)


class TestRegistrationBilling(TestCase):
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

	def test_paid_invoice_is_detected(self):
		invoice = SimpleNamespace(docstatus=1, status="Paid", outstanding_amount=0)

		self.assertTrue(is_invoice_paid(invoice))

	def test_draft_invoice_is_not_paid(self):
		invoice = SimpleNamespace(docstatus=0, status="Paid", outstanding_amount=0)

		self.assertFalse(is_invoice_paid(invoice))

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
