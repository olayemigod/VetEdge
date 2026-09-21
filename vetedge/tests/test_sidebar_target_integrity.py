from __future__ import annotations

from pathlib import Path
from unittest import TestCase

import frappe

from vetedge.install.dashboard import (
	SIDEBAR_TARGET_DOCTYPES,
	_should_keep_sidebar_item,
	ensure_vetedge_workspace_sidebar,
)
from vetedge.install.regulatory_reporting import (
	OUTBREAK_DOCTYPE,
	OUTBREAK_PAGE,
	ensure_regulatory_reporting_navigation,
)

ROOT = Path(__file__).resolve().parents[1]


class TestVetEdgeSidebarTargetIntegrity(TestCase):
	def test_missing_standard_targets_are_not_publishable(self):
		missing = "VetEdge QA Target That Does Not Exist"
		for link_type in SIDEBAR_TARGET_DOCTYPES:
			with self.subTest(link_type=link_type):
				self.assertFalse(
					_should_keep_sidebar_item(
						{
							"type": "Link",
							"label": missing,
							"link_type": link_type,
							"link_to": missing,
						}
					)
				)

	def test_runtime_sidebar_contains_only_existing_standard_targets(self):
		ensure_vetedge_workspace_sidebar()
		sidebar = frappe.get_doc("Workspace Sidebar", "VetEdge")
		checked = 0

		for item in sidebar.items:
			if item.type != "Link" or not item.link_to:
				continue
			target_doctype = SIDEBAR_TARGET_DOCTYPES.get(item.link_type)
			if not target_doctype:
				continue
			checked += 1
			self.assertTrue(
				frappe.db.exists(target_doctype, item.link_to),
				f"Broken sidebar target published: {item.label} -> {item.link_type} {item.link_to}",
			)

		self.assertGreater(checked, 0)

	def test_disease_outbreak_register_uses_edgesuite_page_not_native_list(self):
		ensure_vetedge_workspace_sidebar()
		ensure_regulatory_reporting_navigation()
		self.assertTrue(frappe.db.exists("Page", OUTBREAK_PAGE))

		sidebar = frappe.get_doc("Workspace Sidebar", "VetEdge")
		matches = [item for item in sidebar.items if item.type == "Link" and item.label == "Disease Outbreak Register"]
		self.assertEqual(len(matches), 1)
		self.assertEqual(matches[0].link_type, "Page")
		self.assertEqual(matches[0].link_to, OUTBREAK_PAGE)
		self.assertFalse(
			any(
				item.type == "Link" and item.link_type == "DocType" and item.link_to == OUTBREAK_DOCTYPE
				for item in sidebar.items
			)
		)

	def test_regulatory_pages_follow_professional_veterinary_shell_contract(self):
		regulatory_source = (
			ROOT / "veterinary/page/vetedge_regulatory_reporting/vetedge_regulatory_reporting.js"
		).read_text(encoding="utf-8")
		outbreak_source = (
			ROOT
			/ "veterinary/page/vetedge_disease_outbreak_register/vetedge_disease_outbreak_register.js"
		).read_text(encoding="utf-8")

		for source in (regulatory_source, outbreak_source):
			for expected in (
				"window.VetEdgeProfessionalUI?.install?.()",
				'"EdgeAppShell"',
				'"EdgePageLayout"',
				'"EdgePageHeader"',
				'"EdgeFilterBar"',
				'product: "vetedge"',
				'title: __("Veterinary")',
				"frappe.boot?.vetedge_ui_identity",
			):
				self.assertIn(expected, source)
			self.assertNotIn('productKey: "vetedge"', source)

		self.assertIn('eyebrow: __("Regulatory Reporting")', regulatory_source)
		self.assertIn('title: __("VCN / NADIS Reporting")', regulatory_source)
		self.assertIn('frappe.set_route?.("vetedge-disease-outbreak-register")', regulatory_source)
		self.assertIn('eyebrow: __("Regulatory Reporting")', outbreak_source)
		self.assertIn('title: __("Disease Outbreak Register")', outbreak_source)
		self.assertIn('"EdgeDropdown"', outbreak_source)

	def test_disease_outbreak_register_source_stays_permission_aware_and_edgesuite_native(self):
		page_source = (
			ROOT
			/ "veterinary/page/vetedge_disease_outbreak_register/vetedge_disease_outbreak_register.js"
		).read_text(encoding="utf-8")
		provider_source = (ROOT / "services/outbreak_register.py").read_text(encoding="utf-8")
		list_source = (
			ROOT
			/ "veterinary/doctype/veterinary_disease_outbreak/veterinary_disease_outbreak_list.js"
		).read_text(encoding="utf-8")

		for expected in (
			'frappe.pages["vetedge-disease-outbreak-register"]',
			'"EdgeAppShell"',
			'"EdgeDataTable"',
			'OUTBREAK_REGISTER_API = "vetedge.services.outbreak_register.get_outbreak_register"',
			'searcher: this.searchBranches',
		):
			self.assertIn(expected, page_source)
		self.assertNotIn('frappe.set_route?.("List", OUTBREAK_DOCTYPE)', page_source)

		self.assertIn("normalize_outbreak_report_filters", provider_source)
		self.assertIn("frappe.get_list(", provider_source)
		self.assertIn('fields=[{"COUNT": "*", "as": "total"}]', provider_source)
		self.assertNotIn('fields=["count(name) as total"]', provider_source)
		self.assertNotIn("ignore_permissions=True", provider_source)
		self.assertNotIn("ignore_permissions = True", provider_source)

		self.assertIn('frappe.listview_settings["Veterinary Disease Outbreak"]', list_source)
		self.assertIn('frappe.set_route?.("vetedge-disease-outbreak-register")', list_source)
