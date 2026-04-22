from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services import payment_service
from vetedge.services.payment_backends import processedge_core_backend
from vetedge.services.portal_access import default_portal_settings
from vetedge.services.payment_service import (
	get_payment_status,
	initiate_invoice_payment,
	resolve_payment_backend_mode,
	validate_invoice_payable,
)


class TestPaymentService(TestCase):
	def test_resolve_payment_backend_mode_prefers_explicit_setting(self):
		mode = resolve_payment_backend_mode(
			{
				"payment_backend_mode": "processedge_core",
				"portal_payment_provider_mode": "ERPNext Payment Request",
			}
		)

		self.assertEqual(mode, "processedge_core")

	def test_resolve_payment_backend_mode_supports_legacy_provider_fallback(self):
		mode = resolve_payment_backend_mode(
			{
				"payment_backend_mode": None,
				"portal_payment_provider_mode": "ERPNext Payment Request",
			}
		)

		self.assertEqual(mode, "erpnext_native")

	def test_validate_invoice_payable_returns_sales_invoice_doc_for_owner_context(self):
		invoice_summary = frappe._dict(
			name="SINV-001",
			customer="CUST-001",
			outstanding_amount=150,
			currency="USD",
			docstatus=1,
		)
		invoice_doc = frappe._dict(invoice_summary)
		invoice_doc.company = "Vet Company"

		with (
			patch("vetedge.services.payment_service.validate_owner_invoice_access", return_value=invoice_summary),
			patch("vetedge.services.payment_service.frappe.get_doc", return_value=invoice_doc),
		):
			result = validate_invoice_payable("SINV-001", {"mode": "owner", "owner_context": {"customers": ["CUST-001"]}})

		self.assertEqual(result.name, "SINV-001")
		self.assertEqual(result.company, "Vet Company")

	def test_validate_invoice_payable_rejects_fully_paid_invoice(self):
		invoice_summary = frappe._dict(
			name="SINV-001",
			customer="CUST-001",
			outstanding_amount=0,
			currency="USD",
			docstatus=1,
		)

		with (
			patch("vetedge.services.payment_service.validate_owner_invoice_access", return_value=invoice_summary),
			patch("vetedge.services.payment_service.frappe.throw", side_effect=frappe.ValidationError),
		):
			self.assertRaises(
				frappe.ValidationError,
				validate_invoice_payable,
				"SINV-001",
				{"mode": "owner", "owner_context": {"customers": ["CUST-001"]}},
			)

	def test_initiate_invoice_payment_routes_through_configured_backend(self):
		invoice_doc = frappe._dict(
			name="SINV-001",
			customer="CUST-001",
			outstanding_amount=150,
			currency="USD",
			company="Vet Company",
		)
		backend = SimpleNamespace(
			initiate=lambda context: {
				"success": True,
				"action": "message",
				"payment_provider": "stub",
				"payment_reference": "stub::SINV-001",
				"payment_status_snapshot": "not_started",
				"message": f"Prepared for {context.invoice_name}",
			}
		)

		with (
			patch("vetedge.services.payment_service.get_owner_context", return_value={"customers": ["CUST-001"]}),
			patch(
				"vetedge.services.payment_service.get_portal_settings",
				return_value={"enable_portal_payments": True, "payment_backend_mode": "stub"},
			),
			patch("vetedge.services.payment_service.now_datetime", return_value="2026-04-21 09:00:00"),
			patch("vetedge.services.payment_service.validate_invoice_payable", return_value=invoice_doc),
			patch("vetedge.services.payment_service.get_backend", return_value=backend) as get_backend_mock,
			patch("vetedge.services.payment_service.emit_notification_event", return_value={"queued": False}) as emit_mock,
		):
			result = initiate_invoice_payment("SINV-001")

		self.assertEqual(get_backend_mock.call_args.args[0], "stub")
		self.assertEqual(result["invoice"], "SINV-001")
		self.assertEqual(result["backend_mode"], "stub")
		self.assertEqual(result["payment_provider"], "stub")
		self.assertEqual(result["payment_reference"], "stub::SINV-001")
		self.assertFalse(result["creates_payment_entry"])
		self.assertEqual(emit_mock.call_args.kwargs["payload"]["backend_mode"], "stub")

	def test_initiate_invoice_payment_blocks_unowned_invoice(self):
		with (
			patch("vetedge.services.payment_service.get_owner_context", return_value={"customers": ["CUST-001"]}),
			patch(
				"vetedge.services.payment_service.get_portal_settings",
				return_value={"enable_portal_payments": True, "payment_backend_mode": "stub"},
			),
			patch("vetedge.services.payment_service.validate_invoice_payable", side_effect=frappe.PermissionError),
		):
			self.assertRaises(frappe.PermissionError, initiate_invoice_payment, "SINV-OTHER")

	def test_get_payment_status_routes_to_selected_backend(self):
		backend = SimpleNamespace(get_payment_status=lambda reference: {"reference": reference, "backend_mode": "processedge_core"})

		with (
			patch(
				"vetedge.services.payment_service.get_portal_settings",
				return_value={"enable_portal_payments": True, "payment_backend_mode": "processedge_core"},
			),
			patch("vetedge.services.payment_service.get_backend", return_value=backend) as get_backend_mock,
		):
			result = get_payment_status("pecore::SINV-001")

		self.assertEqual(get_backend_mock.call_args.args[0], "processedge_core")
		self.assertEqual(result["backend_mode"], "processedge_core")

	def test_processedge_core_backend_returns_documented_stub_contract(self):
		context = frappe._dict(
			reference_doctype="Sales Invoice",
			invoice_name="SINV-001",
			customer="CUST-001",
			amount=150,
			currency="USD",
			company="Vet Company",
			access_context={"mode": "owner"},
			source_context={"source": "owner_portal"},
		)

		result = processedge_core_backend.initiate(context)

		self.assertEqual(result["payment_provider"], "processedge_core")
		self.assertEqual(result["payment_reference"], "pecore::SINV-001")
		self.assertFalse(result["creates_payment_entry"])
		self.assertEqual(result["backend_payload"]["request_contract"]["reference_doctype"], "Sales Invoice")
		self.assertEqual(result["backend_payload"]["request_contract"]["currency"], "USD")


class TestPortalPaymentSettingsCompatibility(TestCase):
	def test_portal_settings_use_backend_mode_when_available(self):
		settings = frappe._dict(
			enable_vetedge=1,
			enable_owner_portal=1,
			enable_guest_booking=1,
			allow_owner_cancel_appointment=1,
			allow_owner_reschedule_appointment=0,
			enable_portal_payments=1,
			payment_backend_mode="processedge_core",
			portal_payment_provider_mode="Stub",
			portal_show_consultation_summary_only=1,
			portal_brand_name="BluePaw Vet",
			portal_logo="/files/bluepaw.png",
			portal_primary_color="#1463ff",
			portal_primary_text_color="#ffffff",
			portal_accent_color="#dbeafe",
			portal_page_background="#eff6ff",
			portal_surface_color="#ffffff",
			portal_nav_background="#1e3a8a",
			portal_nav_text_color="#dbeafe",
			portal_muted_text_color="#64748b",
			portal_heading_color="#0f172a",
			portal_card_radius="20px",
			portal_custom_css=".foo { color: red; }",
		)
		meta = SimpleNamespace(has_field=lambda fieldname: True)
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=lambda doctype, name=None, **kwargs: True),
			get_single=lambda doctype: settings,
			get_meta=lambda doctype: meta,
		)

		with patch("vetedge.services.portal_access.frappe", frappe_stub):
			result = payment_service.get_portal_settings()

		self.assertEqual(result["payment_backend_mode"], "processedge_core")
		self.assertEqual(result["portal_payment_provider_mode"], "Stub")
		self.assertEqual(result["portal_theme"]["brand_name"], "BluePaw Vet")
		self.assertEqual(result["portal_theme"]["logo_url"], "/files/bluepaw.png")
		self.assertEqual(result["portal_theme"]["primary_color"], "#1463ff")
		self.assertEqual(result["portal_theme"]["card_radius"], "20px")

	def test_default_portal_settings_include_theme_defaults(self):
		result = default_portal_settings()

		self.assertEqual(result["portal_theme"]["brand_name"], "Owner Portal")
		self.assertEqual(result["portal_theme"]["primary_color"], "#0f766e")
		self.assertEqual(result["portal_theme"]["nav_background"], "#0f172a")
