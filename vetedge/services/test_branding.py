from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.branding import get_clinic_brand_name
from vetedge.services.feature_flags import is_enabled
from vetedge.services.medical_history import get_patient_medical_history_view
from vetedge.services.notifications import get_email_message, get_email_subject
from vetedge.services.registration_billing import get_billing_cost_center


class TestBranding(TestCase):
	def test_get_clinic_brand_name_prefers_portal_brand_name(self):
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=lambda *args, **kwargs: True),
			get_meta=lambda *args, **kwargs: frappe._dict(has_field=lambda fieldname: fieldname == "portal_brand_name"),
			get_single=lambda *args, **kwargs: frappe._dict(portal_brand_name="BluePaw Vet"),
		)

		with patch("vetedge.services.branding.frappe", frappe_stub):
			self.assertEqual(get_clinic_brand_name(), "BluePaw Vet")

	def test_get_clinic_brand_name_falls_back_to_company_name(self):
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(
				exists=lambda *args, **kwargs: False,
				get_value=lambda *args, **kwargs: "Acme Vet Hospital",
			),
		)

		with (
			patch("vetedge.services.branding.frappe", frappe_stub),
			patch("vetedge.services.registration_billing.get_default_company", return_value="Test Company"),
		):
			self.assertEqual(get_clinic_brand_name(), "Acme Vet Hospital")

	def test_notification_subject_and_message_use_clinic_brand(self):
		with patch("vetedge.services.notifications.get_clinic_brand_name", return_value="BluePaw Vet"):
			subject = get_email_subject({"event": "invoice_created"})
			message = get_email_message(
				{
					"event": "invoice_created",
					"reference_doctype": "Sales Invoice",
					"reference_name": "SINV-0001",
					"payload": {"customer": "CUST-0001"},
				}
			)

		self.assertEqual(subject, "BluePaw Vet: Invoice Created")
		self.assertIn("BluePaw Vet", message)

	def test_feature_flag_error_message_is_neutral(self):
		frappe_stub = SimpleNamespace(
			throw=lambda message, exc=None: (_ for _ in ()).throw((exc or frappe.ValidationError)(message)),
			ValidationError=frappe.ValidationError,
		)

		with (
			patch("vetedge.services.feature_flags.frappe", frappe_stub),
			self.assertRaises(frappe.ValidationError) as context,
		):
			is_enabled("unknown_flag")

		self.assertEqual(str(context.exception), "Unknown feature flag: unknown_flag")

	def test_medical_history_vaccinations_are_present_in_view(self):
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(
				exists=lambda *args, **kwargs: True,
				get_value=lambda *args, **kwargs: frappe._dict(
					patient_name="Buddy",
					species="Dog",
					breed="Labrador",
					primary_owner="CUST-001",
					default_branch="Main Branch",
				),
			),
			get_all=lambda *args, **kwargs: [],
			get_list=lambda *args, **kwargs: [],
			get_roles=lambda *args, **kwargs: ["VetEdge Doctor"],
			has_permission=lambda *args, **kwargs: True,
			session=SimpleNamespace(user="doctor@example.com"),
			throw=lambda message, exc=None: (_ for _ in ()).throw((exc or frappe.ValidationError)(message)),
			ValidationError=frappe.ValidationError,
			PermissionError=frappe.PermissionError,
			_dict=frappe._dict,
		)

		with patch("vetedge.services.medical_history.frappe", frappe_stub):
			view = get_patient_medical_history_view("VP-001", "2026-04-01", "2026-04-30")

		self.assertIn("vaccinations", view)
		self.assertEqual(view["vaccinations"], [])

	def test_registration_billing_cost_center_error_message_is_neutral(self):
		def throw(message, exc=None):
			raise (exc or frappe.ValidationError)(message)

		with (
			patch("vetedge.services.registration_billing.get_branch_cost_center", return_value=None),
			patch("vetedge.services.registration_billing.frappe.throw", side_effect=throw),
		):
			with self.assertRaises(frappe.ValidationError) as context:
				get_billing_cost_center("Main", True)

		self.assertEqual(
			str(context.exception),
			"Cost Center is required for Branch Main before billing documents can be created.",
		)
