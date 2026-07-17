from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PAGE_DIRECTORY = (
	REPOSITORY_ROOT
	/ "vetedge"
	/ "veterinary"
	/ "page"
	/ "vetedge_executive_dashboard"
)
LOADER = PAGE_DIRECTORY / "vetedge_executive_dashboard.js"
PAGE_CONFIG = PAGE_DIRECTORY / "vetedge_executive_dashboard.json"
BUNDLE = REPOSITORY_ROOT / "vetedge" / "public" / "js" / "vetedge_executive_dashboard.bundle.js"
COMPONENT = (
	REPOSITORY_ROOT
	/ "vetedge"
	/ "public"
	/ "js"
	/ "vetedge_executive_dashboard"
	/ "VetedgeExecutiveDashboard.vue"
)
SERVER_API = REPOSITORY_ROOT / "vetedge" / "services" / "reporting_logic_v4.py"


class TestVetedgeExecutiveDashboardEdgeUI(TestCase):
	def test_page_config_and_assets_exist(self):
		config = json.loads(PAGE_CONFIG.read_text(encoding="utf-8"))

		self.assertEqual(config["name"], "vetedge-executive-dashboard")
		self.assertEqual(config["module"], "Veterinary")
		for path in (LOADER, BUNDLE, COMPONENT, SERVER_API):
			self.assertTrue(path.exists(), path)

	def test_loader_uses_standalone_edgesuite_runtime_before_product_bundle(self):
		content = LOADER.read_text(encoding="utf-8")

		self.assertIn("window.EdgeSuiteUI || window.EdgeUI", content)
		self.assertIn("runtime?.createEdgeApp", content)
		self.assertIn("runtime?.components", content)
		self.assertIn("edgeui.bundle.js", content)
		self.assertIn("vetedge_executive_dashboard.bundle.js", content)
		self.assertLess(content.index("edgeui.bundle.js"), content.index("vetedge_executive_dashboard.bundle.js"))
		self.assertIn("wrapper.current_visit_id", content)
		self.assertIn("unmount()", content)
		self.assertNotIn("dashboard_shell.js", content)
		self.assertNotIn("coreedge", content.lower())

	def test_bundle_mounts_component_through_edgesuite_ui(self):
		content = BUNDLE.read_text(encoding="utf-8")

		self.assertIn("window.EdgeSuiteUI || window.EdgeUI", content)
		self.assertIn("VetedgeExecutiveDashboard.components = runtime.components", content)
		self.assertIn("runtime.createEdgeApp(VetedgeExecutiveDashboard)", content)
		self.assertNotIn("import { createApp } from 'vue'", content)
		self.assertNotIn("coreedge", content.lower())

	def test_component_uses_shared_states_cards_and_branch_filters(self):
		content = COMPONENT.read_text(encoding="utf-8")

		for component in (
			"EdgeAppShell",
			"EdgePageLayout",
			"EdgePageHeader",
			"EdgeFilterBar",
			"EdgeStatCard",
			"EdgeLoadingState",
			"EdgeEmptyState",
			"EdgeErrorState",
		):
			self.assertIn(component, content)

		self.assertIn("filters.branch", content)
		self.assertIn("from_date", content)
		self.assertIn("to_date", content)
		self.assertIn("dashboard_key: 'executive'", content)
		self.assertIn("reporting_logic_v4.get_dashboard_payload", content)
		self.assertIn('data-edge-product="vetedge"', content)
		self.assertNotIn("frappe.EdgeSuite.DateRanges", content)
		self.assertNotIn("coreedge", content.lower())

	def test_server_api_normalizes_branch_aware_filters(self):
		content = SERVER_API.read_text(encoding="utf-8")

		self.assertIn("def get_dashboard_payload", content)
		self.assertIn("normalize_dashboard_filters(key, filters)", content)
		self.assertIn('if key == "executive":', content)
