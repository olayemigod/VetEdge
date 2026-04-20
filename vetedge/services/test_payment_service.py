from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.payment_service import initiate_invoice_payment, validate_portal_invoice_payment_eligibility


class TestPaymentService(TestCase):
	def test_payment_initiation_returns_provider_agnostic_stub_payload(self):
		invoice = frappe._dict(
			name="SINV-001",
			customer="CUST-001",
			outstanding_amount=150,
			currency="NGN",
			docstatus=1,
		)

		with (
			patch("vetedge.services.payment_service.get_owner_context", return_value={"customers": ["CUST-001"]}),
			patch(
				"vetedge.services.payment_service.get_portal_settings",
				return_value={"enable_portal_payments": True, "portal_payment_provider_mode": "Stub"},
			),
			patch("vetedge.services.payment_service.validate_portal_invoice_payment_eligibility", return_value=invoice),
			patch("vetedge.services.payment_service.emit_notification_event", return_value={"queued": False}),
		):
			payload = initiate_invoice_payment("SINV-001")

		self.assertEqual(payload["invoice"], "SINV-001")
		self.assertEqual(payload["amount"], 150.0)
		self.assertEqual(payload["provider"], "Stub")
		self.assertFalse(payload["creates_payment_entry"])

	def test_payment_initiation_blocks_when_portal_payments_disabled(self):
		with (
			patch("vetedge.services.payment_service.get_owner_context", return_value={"customers": ["CUST-001"]}),
			patch(
				"vetedge.services.payment_service.get_portal_settings",
				return_value={"enable_portal_payments": False, "portal_payment_provider_mode": "Stub"},
			),
			patch("vetedge.services.payment_service.frappe.throw", side_effect=frappe.PermissionError),
		):
			self.assertRaises(frappe.PermissionError, initiate_invoice_payment, "SINV-001")

	def test_payment_eligibility_rejects_paid_invoice(self):
		invoice = frappe._dict(
			name="SINV-001",
			customer="CUST-001",
			outstanding_amount=0,
			currency="NGN",
			docstatus=1,
		)

		with (
			patch("vetedge.services.payment_service.validate_owner_invoice_access", return_value=invoice),
			patch("vetedge.services.payment_service.frappe.throw", side_effect=frappe.ValidationError),
		):
			self.assertRaises(
				frappe.ValidationError,
				validate_portal_invoice_payment_eligibility,
				"SINV-001",
				{"customers": ["CUST-001"]},
			)
