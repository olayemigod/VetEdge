from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def source(relative_path: str) -> str:
	return (ROOT / relative_path).read_text(encoding="utf-8")


class TestEdgeSuiteDestinationCoverageContract(unittest.TestCase):
	def test_boot_sidebar_rewrites_configuration_destinations_to_edgesuite_pages(self):
		text = source("vetedge/ui_identity.py")
		for doctype, page in {
			"Veterinary Care Location": "vetedge-care-locations",
			"Branch User Assignment": "vetedge-branch-user-access",
			"Branch Practitioner Assignment": "vetedge-practitioner-coverage",
			"Veterinary Notification Preference": "vetedge-notification-preferences",
			"Veterinary Notification Log": "vetedge-notification-delivery-log",
			"Veterinary Notification Item": "vetedge-notification-items",
			"Veterinary Role Bundle": "vetedge-role-bundles",
			"Veterinary License Profile": "vetedge-license-profile",
		}.items():
			with self.subTest(doctype=doctype):
				self.assertIn(f'"{doctype}": "{page}"', text)
		self.assertIn('item["link_type"] = "Page"', text)
		self.assertIn('_align_edge_sidebar_destinations(bootinfo)', text)

	def test_administration_page_uses_edgesuite_and_permission_aware_provider(self):
		page = source("vetedge/veterinary/page/vetedge_administration/vetedge_administration.js")
		provider = source("vetedge/services/administration_workspace.py")
		for token in (
			"EdgeAppShell",
			"EdgeDataTable",
			"EdgeDocumentForm",
			"get_administration_page",
			"get_administration_document",
			"save_administration_document",
			"delete_administration_document",
		):
			self.assertIn(token, page if token.startswith("Edge") else provider)
		self.assertIn('"mode": "single_readonly"', provider)
		self.assertIn('"system_manager_only": True', provider)
		self.assertIn('This administration resource is read-only.', provider)
		self.assertIn("require_vetedge_platform_access", provider)

	def test_configuration_aliases_route_router_first_to_shared_workspaces(self):
		aliases = {
			"vetedge_branch_user_access/vetedge_branch_user_access.js": "user-assignments",
			"vetedge_practitioner_coverage/vetedge_practitioner_coverage.js": "practitioner-assignments",
			"vetedge_notification_preferences/vetedge_notification_preferences.js": "notification-preferences",
			"vetedge_notification_delivery_log/vetedge_notification_delivery_log.js": "notification-logs",
			"vetedge_notification_items/vetedge_notification_items.js": "notification-items",
			"vetedge_role_bundles/vetedge_role_bundles.js": "role-bundles",
			"vetedge_license_profile/vetedge_license_profile.js": "license-profile",
		}
		base = "vetedge/veterinary/page/"
		for path, resource in aliases.items():
			with self.subTest(path=path):
				text = source(base + path)
				self.assertIn(f"resource={resource}", text)
				self.assertIn("history.replaceState", text)
				self.assertIn("frappe.router.route", text)

	def test_sidebar_reports_have_edgesuite_provider_coverage(self):
		registry = source("vetedge/public/js/vetedge_report_provider_registry.js")
		alignment = source("vetedge/public/js/vetedge_sidebar_qa_alignment.js")
		for report in (
			"Owner Register",
			"Patient Register",
			"Consultation Register",
			"Lab Order Report",
			"Vaccination Report",
			"Active Hospitalisations",
			"Hospitalisation Charge Summary",
			"Care Location Occupancy",
			"Hospitalisation Discharge Watch",
			"Pending Hospitalisation Actions",
			"Grooming Report",
			"Boarding Report",
			"Kennel Availability Report",
			"Practitioner Performance Report",
			"Branch Performance Report",
			"Unpaid Invoice Report",
			"Revenue Summary",
			"Stock Usage Summary",
			"Stock Expiry Status",
			"Dispensary Activity Report",
			"Veterinary Notification Event Registry",
		):
			with self.subTest(report=report):
				self.assertIn(report, registry)
				self.assertIn(report, alignment)
		self.assertIn("get_legacy_report_page", registry)
		self.assertIn("materialize-then-slice", registry)

	def test_report_filter_runtime_covers_specialist_fields_and_saved_view_state(self):
		filters = source("vetedge/public/js/vetedge_report_filter_ui.js")
		search = source("vetedge/services/report_filter_search.py")
		for key in (
			"cost_center",
			"age_range",
			"kennel",
			"assigned_staff",
			"care_location",
			"attending_veterinarian",
			"admission_date_from",
			"admission_date_to",
			"invoice_status",
			"minimum_days_admitted",
			"warehouse",
			"company",
			"item_group",
			"expiry_buckets",
			"include_zero_qty",
		):
			with self.subTest(key=key):
				self.assertIn(key, filters)
		self.assertIn("REPORT_FILTER_KEYS.push(key)", filters)
		self.assertIn('type: "input"', filters)
		self.assertIn("EdgeInput", filters)
		for field in ("kennel", "care_location", "warehouse", "cost_center", "company", "item_group"):
			self.assertIn(f'"{field}"', search)
		self.assertIn('field in {"kennel", "care_location"}', search)
		self.assertIn('filters["branch"] = normalized.get("branch")', search)
		self.assertIn('field in {"customer", "owner"}', search)
		self.assertIn('field == "assigned_staff"', search)


if __name__ == "__main__":
	unittest.main()
