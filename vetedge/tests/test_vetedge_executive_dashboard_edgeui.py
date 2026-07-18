from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PAGE_DIRECTORY = REPOSITORY_ROOT / "vetedge" / "veterinary" / "page" / "vetedge_executive_dashboard"
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
PRODUCT_MENU = REPOSITORY_ROOT / "vetedge" / "public" / "js" / "edgesuite_product_menu.js"
SERVER_API = REPOSITORY_ROOT / "vetedge" / "services" / "reporting_logic_v4.py"


class TestVetedgeExecutiveDashboardEdgeUI(TestCase):
	def read(self, path):
		return path.read_text(encoding="utf-8")

	def test_page_config_and_assets_exist(self):
		config = json.loads(self.read(PAGE_CONFIG))
		self.assertEqual(config["name"], "vetedge-executive-dashboard")
		self.assertEqual(config["module"], "Veterinary")
		for path in (LOADER, BUNDLE, COMPONENT, PRODUCT_MENU, SERVER_API):
			self.assertTrue(path.exists(), path)

	def test_loader_uses_complete_standalone_runtime_contract(self):
		content = self.read(LOADER)
		for required in (
			"window.EdgeSuiteUI || window.EdgeUI",
			"runtime?.createEdgeApp",
			"runtime?.components",
			"EdgeDashboardLayout",
			"EdgeNotificationBell",
			"EdgeNotificationDrawer",
			"edgeui.bundle.js",
			"vetedge_executive_dashboard.bundle.js",
			"wrapper.current_visit_id",
			"unmount()",
		):
			self.assertIn(required, content)
		self.assertLess(content.index("edgeui.bundle.js"), content.index("vetedge_executive_dashboard.bundle.js"))
		self.assertNotIn("dashboard_shell.js", content)
		self.assertNotIn("coreedge", content.lower())

	def test_bundle_mounts_component_through_edgesuite_ui(self):
		content = self.read(BUNDLE)
		self.assertIn("window.EdgeSuiteUI || window.EdgeUI", content)
		self.assertIn("VetedgeExecutiveDashboard.components = runtime.components", content)
		self.assertIn("runtime.createEdgeApp(VetedgeExecutiveDashboard)", content)
		self.assertNotIn("import { createApp } from 'vue'", content)
		self.assertNotIn("coreedge", content.lower())

	def test_product_menu_and_notification_actions_are_present(self):
		component = self.read(COMPONENT)
		product_menu = self.read(PRODUCT_MENU)
		self.assertIn(':menuItems="menuItems"', component)
		self.assertIn("window.VetedgeProductMenu?.mount?.()", component)
		self.assertIn("EdgeNotificationBell", component)
		self.assertIn("EdgeNotificationDrawer", component)
		self.assertIn("notificationApi", component)
		self.assertIn("window.VetedgeProductMenu", product_menu)
		self.assertIn("mount: () => mount(0)", product_menu)

	def test_vetedge_theming_and_full_width_layout_contract(self):
		content = self.read(COMPONENT)
		self.assertIn('product="vetedge"', content)
		self.assertIn('data-edge-product="vetedge"', content)
		self.assertIn("--edge-primary:", content)
		self.assertIn("--edge-primary-soft:", content)
		self.assertIn("linear-gradient", content)
		self.assertIn(".vetedge-executive-dashboard-root .edge-shell-main", content)
		self.assertIn("width: 100%", content)
		self.assertIn("max-width: none", content)

	def test_date_presets_branch_filters_and_route_options_are_preserved(self):
		content = self.read(COMPONENT)
		for label in (
			"Today",
			"This Week",
			"This Month",
			"Last 30 Days",
			"This Quarter",
			"This Year",
			"Custom Period",
		):
			self.assertIn(label, content)
		for contract in ("filters.branch", "date_preset", "from_date", "to_date", "frappe.route_options"):
			self.assertIn(contract, content)

	def test_responsive_kpi_grid_and_edgesuite_controls_are_used(self):
		content = self.read(COMPONENT)
		for component in (
			"EdgeAppShell",
			"EdgePageLayout",
			"EdgePageHeader",
			"EdgeFilterBar",
			"EdgeDashboardLayout",
			"EdgeStatCard",
			"EdgeLoadingState",
			"EdgeEmptyState",
			"EdgeErrorState",
		):
			self.assertIn(component, content)
		self.assertIn("repeat(auto-fit, minmax(180px, 1fr))", content)
		self.assertIn("edge-select edge-control", content)
		self.assertIn("edge-input edge-control", content)
		self.assertIn("edge-button edge-button--primary", content)

	def test_existing_api_report_chart_and_currency_workflows_are_preserved(self):
		content = self.read(COMPONENT)
		self.assertIn("vetedge.services.reporting_logic_v4.get_dashboard_payload", content)
		self.assertIn("dashboard_key: 'executive'", content)
		self.assertIn("frappe.set_route('query-report', report)", content)
		self.assertIn("new frappe.Chart", content)
		self.assertIn("renderChartTable", content)
		self.assertIn("new Intl.NumberFormat", content)
		self.assertNotIn("frappe.format_value", content)

	def test_server_api_normalizes_branch_aware_filters(self):
		content = self.read(SERVER_API)
		self.assertIn("def get_dashboard_payload", content)
		self.assertIn("normalize_dashboard_filters(key, filters)", content)
		self.assertIn('if key == "executive":', content)

	def test_no_coreedge_frontend_dependency(self):
		for path in (LOADER, BUNDLE, COMPONENT, PRODUCT_MENU):
			self.assertNotIn("coreedge/", self.read(path).lower())
