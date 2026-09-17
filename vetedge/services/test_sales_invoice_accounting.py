from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services import sales_invoice_accounting as accounting


class _BaseSalesInvoice:
	def __init__(self, **values):
		self._values = dict(values)
		for key, value in values.items():
			setattr(self, key, value)

	def get(self, fieldname, default=None):
		return getattr(self, fieldname, self._values.get(fieldname, default))

	def set_missing_values(self, for_validate: bool = False):
		self.base_set_missing_user = frappe.session.user
		self.set_missing_lead_customer_details(for_validate)
		return "base-missing-values"

	def set_missing_lead_customer_details(self, for_validate: bool = False):
		self.base_party_details_user = frappe.session.user
		return "base-party-details"


class _Invoice(accounting.VetEdgeSalesInvoiceBillingMixin, _BaseSalesInvoice):
	pass


class TestVetEdgeSalesInvoiceAccounting(TestCase):
	def setUp(self):
		self._session = deepcopy(frappe.local.session)
		self._attrs = {
			name: getattr(frappe.local, name)
			for name in accounting._USER_CONTEXT_ATTRS
			if hasattr(frappe.local, name)
		}
		frappe.local.session = frappe._dict(
			user="doctor@example.com",
			sid="real-session-id",
			data=frappe._dict(keep="session-data"),
		)
		frappe.local.form_dict = frappe._dict(cmd="vetedge.services.resource_center.save_resource_record")
		frappe.local.cache = {"keep": "cache"}
		frappe.local.role_permissions = {"keep": "roles"}
		frappe.local.new_doc_templates = {"keep": "templates"}
		frappe.local.user_perms = {"keep": "permissions"}

	def tearDown(self):
		frappe.local.session = self._session
		for name, value in self._attrs.items():
			setattr(frappe.local, name, value)

	@staticmethod
	def _fake_set_user(user: str):
		frappe.local.session.user = user
		frappe.local.session.sid = user
		frappe.local.session.data = frappe._dict()
		frappe.local.cache = {}
		frappe.local.form_dict = frappe._dict()
		frappe.local.role_permissions = {}
		frappe.local.new_doc_templates = {}
		frappe.local.user_perms = None

	def test_billing_core_invoice_resolves_account_as_system_then_restores_actor(self):
		invoice = _Invoice(
			remarks="VetEdge billing session VBS-2026-00001",
			customer="CUST-001",
			company="Mercy and Grace Veterinary World",
			debit_to=None,
		)
		resolver_users = []

		def resolve_account(party_type, party, company):
			resolver_users.append(frappe.session.user)
			self.assertEqual(party_type, "Customer")
			self.assertEqual(party, "CUST-001")
			return "Debtors - MGV"

		with (
			patch.object(accounting.frappe, "set_user", side_effect=self._fake_set_user),
			patch.object(accounting, "get_party_account", side_effect=resolve_account),
			patch.object(accounting.frappe.db, "get_value", return_value="NGN"),
		):
			result = invoice.set_missing_values()

		self.assertEqual(result, "base-missing-values")
		self.assertEqual(resolver_users, ["Administrator"])
		self.assertEqual(invoice.debit_to, "Debtors - MGV")
		self.assertEqual(invoice.party_account_currency, "NGN")
		self.assertEqual(invoice.base_set_missing_user, "doctor@example.com")
		self.assertEqual(invoice.base_party_details_user, "Administrator")
		self.assertEqual(frappe.session.user, "doctor@example.com")
		self.assertEqual(frappe.session.sid, "real-session-id")
		self.assertEqual(frappe.session.data.get("keep"), "session-data")
		self.assertEqual(frappe.form_dict.get("cmd"), "vetedge.services.resource_center.save_resource_record")
		self.assertEqual(frappe.local.cache.get("keep"), "cache")
		self.assertEqual(frappe.local.role_permissions.get("keep"), "roles")

	def test_manual_sales_invoice_keeps_normal_user_permission_context(self):
		invoice = _Invoice(
			remarks="Manual invoice",
			customer="CUST-001",
			company="Mercy and Grace Veterinary World",
			debit_to=None,
		)
		with patch.object(accounting, "get_party_account") as get_party_account:
			invoice.set_missing_values()

		get_party_account.assert_not_called()
		self.assertEqual(invoice.base_set_missing_user, "doctor@example.com")
		self.assertEqual(invoice.base_party_details_user, "doctor@example.com")
		self.assertEqual(frappe.session.user, "doctor@example.com")

	def test_account_resolution_failure_restores_request_context(self):
		invoice = _Invoice(
			remarks="VetEdge billing session VBS-2026-00002",
			customer="CUST-002",
			company="Mercy and Grace Veterinary World",
			debit_to=None,
		)
		with (
			patch.object(accounting.frappe, "set_user", side_effect=self._fake_set_user),
			patch.object(accounting, "get_party_account", side_effect=frappe.PermissionError("account")),
			self.assertRaises(frappe.PermissionError),
		):
			invoice.set_missing_values()

		self.assertEqual(frappe.session.user, "doctor@example.com")
		self.assertEqual(frappe.session.sid, "real-session-id")
		self.assertEqual(frappe.form_dict.get("cmd"), "vetedge.services.resource_center.save_resource_record")

	def test_processedge_veterinary_future_billing_marker_is_supported(self):
		invoice = _Invoice(
			remarks="ProcessEdge Veterinary billing session VBS-2026-00003",
			customer="CUST-003",
			company="Test Company",
			debit_to="Debtors - TC",
		)
		self.assertTrue(accounting.is_vetedge_billing_core_invoice(invoice))

	def test_hook_extends_sales_invoice_without_replacing_erpnext_controller(self):
		hooks = (Path(__file__).resolve().parents[1] / "hooks.py").read_text(encoding="utf-8")
		self.assertIn('extend_doctype_class = {', hooks)
		self.assertIn('"Sales Invoice": ["vetedge.services.sales_invoice_accounting.VetEdgeSalesInvoiceBillingMixin"]', hooks)
		self.assertNotIn('override_doctype_class = {\n\t"Sales Invoice"', hooks)
