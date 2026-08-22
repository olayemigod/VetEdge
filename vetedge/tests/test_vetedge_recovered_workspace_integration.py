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
from vetedge.services.service_operations import get_service_operations_page
from vetedge.services.settings_page import get_veterinary_settings_page


class TestRecoveredEdgeSuiteWorkspaces(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._feature_flags = {
			fieldname: frappe.db.get_single_value("Veterinary Settings", fieldname)
			for fieldname in ("enable_vetedge", "enable_appointments", "enable_consultations")
		}
		for fieldname in self._feature_flags:
			frappe.db.set_single_value("Veterinary Settings", fieldname, 1, update_modified=False)

	def tearDown(self):
		for fieldname, value in self._feature_flags.items():
			frappe.db.set_single_value("Veterinary Settings", fieldname, value or 0, update_modified=False)
		frappe.set_user("Administrator")

	def test_recovered_standard_pages_exist_after_migrate(self):
		for page in (
			"vetedge",
			"veterinary-settings-center",
			"vetedge-master-workspace",
			"vetedge-pricing-master-workspace",
			"vetedge-front-desk-action-center",
			"vetedge-clinical-workspace",
			"veterinary-medical-history",
			"vetedge-service-operations",
		):
			with self.subTest(page=page):
				self.assertTrue(frappe.db.exists("Page", page), page)

	def test_hospitalisation_dashboard_stays_removed_but_vitals_and_medical_history_remain(self):
		self.assertFalse(frappe.db.exists("Page", "veterinary-hospitalisation-dashboard"))
		self.assertTrue(frappe.db.exists("Workspace Sidebar", "VetEdge"))
		sidebar = frappe.get_doc("Workspace Sidebar", "VetEdge")
		links = {(row.link_type, row.link_to) for row in sidebar.get("items") if row.link_to}
		self.assertNotIn(("Page", "veterinary-hospitalisation-dashboard"), links)
		self.assertIn(("DocType", "Veterinary Vital Signs"), links)
		self.assertIn(("Page", "veterinary-medical-history"), links)
		self.assertTrue(any(row.type == "Section Break" and row.label == "Hospital & Services" for row in sidebar.get("items")))

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

	def test_hospital_services_resources_execute_permission_aware_list_contracts(self):
		resources = (
			"boarding-bookings",
			"boarding-stays",
			"boarding-care-records",
			"grooming-appointments",
			"grooming-sessions",
		)
		for resource in resources:
			with self.subTest(resource=resource):
				listing = get_service_operations_page(resource, page_length=3)
				self.assertEqual(listing["resource"], resource)
				self.assertIn("columns", listing)
				self.assertIn("rows", listing)
				self.assertEqual(listing["page_length"], 3)

		boarding = get_service_operations_page("boarding-bookings", page_length=1)
		grooming = get_service_operations_page("grooming-appointments", page_length=1)
		self.assertEqual(boarding["editor_resource"], "boarding")
		self.assertEqual(grooming["editor_resource"], "grooming")
		self.assertTrue(boarding["can_create"])
		self.assertTrue(grooming["can_create"])

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
