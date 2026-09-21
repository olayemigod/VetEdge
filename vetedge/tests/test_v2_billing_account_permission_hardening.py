from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services import billing_core, billing_modal


class TestV2BillingAccountPermissionHardening(TestCase):
	def test_trusted_receivable_resolver_uses_company_default_without_account_visibility_check(self):
		def cached_value(doctype, name, fieldname, as_dict=False, **kwargs):
			if doctype == "Customer" and fieldname == "customer_group":
				return "All Customer Groups"
			if doctype == "Company" and fieldname == "default_receivable_account":
				return "Debtors - A"
			if doctype == "Account" and fieldname == "account_currency":
				return "NGN"
			if doctype == "Account" and isinstance(fieldname, list):
				return frappe._dict(
					company="Company A",
					account_type="Receivable",
					report_type="Balance Sheet",
					account_currency="NGN",
					is_group=0,
					disabled=0,
				)
			return None

		with (
			patch("vetedge.services.billing_core.frappe.db.get_value", return_value=None),
			patch("vetedge.services.billing_core.frappe.get_cached_value", side_effect=cached_value),
			patch("erpnext.accounts.party.get_party_gle_currency", return_value=None),
			patch("erpnext.accounts.party.get_party_gle_account", return_value=None),
		):
			account = billing_core.resolve_trusted_customer_receivable_account("CUST-001", "Company A")

		self.assertEqual(account, "Debtors - A")

	def test_trusted_receivable_account_is_prefilled_on_draft_invoice(self):
		invoice = frappe._dict(
			doctype="Sales Invoice",
			docstatus=0,
			customer="CUST-001",
			company="Company A",
			debit_to=None,
		)

		with (
			patch(
				"vetedge.services.billing_core.resolve_trusted_customer_receivable_account",
				return_value="Debtors - A",
			),
			patch(
				"vetedge.services.billing_core.frappe.get_cached_value",
				return_value="NGN",
			),
		):
			account = billing_core.apply_trusted_customer_receivable_account(invoice)

		self.assertEqual(account, "Debtors - A")
		self.assertEqual(invoice.debit_to, "Debtors - A")
		self.assertEqual(invoice.party_account_currency, "NGN")

	def test_mode_of_payment_resolves_company_cash_or_bank_account(self):
		with (
			patch(
				"erpnext.accounts.doctype.sales_invoice.sales_invoice.get_bank_cash_account",
				return_value={"account": "Cash - A"},
			),
			patch(
				"vetedge.services.billing_modal.frappe.get_cached_value",
				return_value=frappe._dict(
					company="Company A",
					account_type="Cash",
					is_group=0,
					disabled=0,
				),
			),
		):
			account = billing_modal.resolve_modal_payment_destination_account(
				"Company A",
				"Cash",
			)

		self.assertEqual(account, "Cash - A")

	def test_non_accounting_user_cannot_override_payment_destination(self):
		with (
			patch("vetedge.services.billing_modal.can_override_payment_account", return_value=False),
			patch("vetedge.services.billing_modal.frappe.throw", side_effect=frappe.PermissionError),
		):
			self.assertRaises(
				frappe.PermissionError,
				billing_modal.resolve_modal_payment_destination_account,
				"Company A",
				"Cash",
				"Another Cash - A",
			)
