from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from vetedge.services.clinical_workspace import get_clinical_summary, get_consultations
from vetedge.services.clinical_workspace_context import get_clinical_context_options
from vetedge.services.front_desk_action_center import get_front_desk_summary, get_guest_requests
from vetedge.services.master_workspace import get_master_definition, get_master_list
from vetedge.services.pricing_master_workspace import (
	get_pricing_master_definition,
	get_pricing_master_list,
)
from vetedge.services.settings_page import get_veterinary_settings_page


class TestRecoveredEdgeSuiteWorkspaces(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_recovered_standard_pages_exist_after_migrate(self):
		for page in (
			"vetedge",
			"veterinary-settings-center",
			"vetedge-master-workspace",
			"vetedge-pricing-master-workspace",
			"vetedge-front-desk-action-center",
			"vetedge-clinical-workspace",
		):
			with self.subTest(page=page):
				self.assertTrue(frappe.db.exists("Page", page), page)

	def test_settings_provider_exposes_branding_and_editable_schema(self):
		payload = get_veterinary_settings_page()
		self.assertEqual(payload["doctype"], "Veterinary Settings")
		self.assertTrue(payload["schema"])
		self.assertIsInstance(payload["values"], dict)
		self.assertIn("portal_brand_name", payload["values"])
		self.assertIn("portal_logo", payload["values"])
		self.assertTrue(payload["can_write"])

	def test_all_recovered_master_resources_execute_definition_and_list_contracts(self):
		for resource in (
			"species",
			"breeds",
			"symptoms",
			"diagnosis-categories",
			"diagnoses",
			"service-types",
			"consultation-types",
		):
			with self.subTest(resource=resource):
				definition = get_master_definition(resource)
				listing = get_master_list(resource, page_length=3)
				self.assertEqual(definition["resource"], resource)
				self.assertTrue(definition["permissions"]["read"])
				self.assertIn("rows", listing)
				self.assertEqual(listing["page_length"], 3)

	def test_all_recovered_pricing_resources_execute_definition_and_list_contracts(self):
		for resource in (
			"treatment-items",
			"treatment-types",
			"lab-tests",
			"vaccines",
			"grooming-services",
		):
			with self.subTest(resource=resource):
				definition = get_pricing_master_definition(resource)
				listing = get_pricing_master_list(resource, page_length=3)
				self.assertEqual(definition["resource"], resource)
				self.assertTrue(definition["permissions"]["read"])
				self.assertIn("rows", listing)
				self.assertEqual(listing["page_length"], 3)

	def test_front_desk_provider_executes_on_clean_site(self):
		summary = get_front_desk_summary()
		listing = get_guest_requests(page_length=3)
		for key in ("guest_requests", "today_appointments", "open_missed", "reference_date"):
			self.assertIn(key, summary)
		self.assertIn("rows", listing)
		self.assertEqual(listing["page_length"], 3)

	def test_clinical_provider_and_context_execute_on_clean_site(self):
		summary = get_clinical_summary()
		listing = get_consultations(page_length=3)
		for key in ("draft", "in_progress", "awaiting_payment", "ready_for_treatment", "completed"):
			self.assertIn(key, summary)
		self.assertIn("rows", listing)
		self.assertEqual(listing["page_length"], 3)
		self.assertIsInstance(get_clinical_context_options("practitioner", limit=3), list)
		self.assertIsInstance(get_clinical_context_options("consultation_type", limit=3), list)
