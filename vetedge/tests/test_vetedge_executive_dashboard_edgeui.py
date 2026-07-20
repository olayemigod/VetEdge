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
STOCK_COMPONENT = (
	REPOSITORY_ROOT
	/ "vetedge"
	/ "public"
	/ "js"
	/ "vetedge_stock_expiry_monitor"
	/ "VetedgeStockExpiryMonitor.vue"
)
HOOKS = REPOSITORY_ROOT / "vetedge" / "hooks.py"
SERVER_API = REPOSITORY_ROOT / "vetedge" / "services" / "reporting_logic_v4.py"
DASHBOARD_STYLES = REPOSITORY_ROOT / "vetedge" / "public" / "css" / "dashboard_shell.css"
UNREAD_BADGE_STYLES = REPOSITORY_ROOT / "vetedge" / "public" / "css" / "veterinary_unread_badge.css"


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

	def test_product_menu_is_global_descriptive_and_veterinary_facing(self):
		component = self.read(COMPONENT)
		product_menu = self.read(PRODUCT_MENU)
		hooks = self.read(HOOKS)
		self.assertNotIn(':menuItems="menuItems"', component)
		self.assertIn("window.VetedgeProductMenu?.mount?.()", component)
		self.assertIn("EdgeNotificationBell", component)
		self.assertIn("EdgeNotificationDrawer", component)
		self.assertIn("window.VetedgeProductMenu", product_menu)
		for public_method in ("mount,", "unmount,", "remount,"):
			self.assertIn(public_method, product_menu)
		for contract in (
			'".page-head .page-actions"',
			'"header .navbar .navbar-right"',
			"vetedge-product-menu-waffle-icon",
			"<circle",
			"target.node.prepend(slot)",
			"vetedge-product-menu-quick-access",
			"vetedge-product-menu-quick-grid",
			"vetedge-product-menu-grid",
			"vetedge-product-menu-section-links",
			"Quick access",
			"Veterinary workspace",
			"function menuIcon(icon)",
			"MENU_ICON_GLYPHS",
			"MENU_DESCRIPTIONS",
			"description: menuDescription(item)",
			"veterinary-owned-mega-menu",
		):
			self.assertIn(contract, product_menu)
		self.assertNotIn('html(item.link_type || "Workspace")', product_menu)
		self.assertNotIn("runtime.registerProductMenu", product_menu)
		self.assertIn("/assets/vetedge/js/edgesuite_product_menu.js", hooks)

	def test_product_menu_is_idempotent_and_lifecycle_aware(self):
		product_menu = self.read(PRODUCT_MENU)
		for contract in (
			"removeDuplicates",
			"already-mounted",
			"toolbar_setup",
			"page-change",
			"desktop_screen",
			"sidebar_setup",
			"MutationObserver",
			"function diagnose()",
			"lastMountResult",
			"currentMenuNodeCount",
			"FALLBACK_ROUTES",
			"configured_routes",
			"vetedge-product-menu-slot--floating",
			'"navbar-became-visible"',
			'result(true, "inserted"',
			'result(false, "no-navbar-target"',
		):
			self.assertIn(contract, product_menu)
		self.assertNotIn("frappe.realtime", product_menu)
		self.assertNotIn("socket", product_menu.lower())

	def test_shared_shell_and_notification_contract_is_present(self):
		for content in (self.read(COMPONENT), self.read(STOCK_COMPONENT)):
			self.assertIn("EdgeAppShell", content)
			self.assertNotIn(':menuItems="menuItems"', content)
			self.assertIn("EdgeNotificationBell", content)
			self.assertIn("EdgeNotificationDrawer", content)
			self.assertIn('product="vetedge"', content)
			self.assertIn('data-edge-product="vetedge"', content)
			self.assertIn("window.VetedgeProductMenu", content)
			self.assertIn("tenantName", content)
			self.assertIn("branchName", content)
			self.assertIn("userName", content)
			self.assertNotIn("coreedge/", content.lower())

	def test_responsive_layout_and_edgesuite_controls_are_preserved(self):
		content = self.read(COMPONENT)
		styles = self.read(DASHBOARD_STYLES)
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
		for contract in (
			"repeat(auto-fit, minmax(180px, 1fr))",
			"width: 100% !important",
			"max-width: none !important",
			"container-type: inline-size",
			"@container vetedge-executive-content",
		):
			self.assertIn(contract, content)
		for contract in (
			"box-sizing: border-box",
			"width: 100%",
			"max-width: none",
			"min-width: 0",
			"flex: 1 1 auto",
			"repeat(4, minmax(0, 1fr))",
			"repeat(2, minmax(0, 1fr))",
			"grid-template-columns: minmax(0, 1fr)",
		):
			self.assertIn(contract, styles)
		self.assertNotIn("calc(100% -", styles)

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

	def test_sidebar_badge_and_no_coreedge_contracts_are_preserved(self):
		badge_styles = self.read(UNREAD_BADGE_STYLES)
		for contract in (
			".layout-side-section.collapsed",
			".body-sidebar.sidebar-collapsed",
			'[data-sidebar-collapsed="true"]',
			'body:has([data-edge-product="vetedge"])',
			".veterinary-unread-bell-badge-label",
			"display: none",
		):
			self.assertIn(contract, badge_styles)
		for path in (LOADER, BUNDLE, COMPONENT, STOCK_COMPONENT, PRODUCT_MENU):
			self.assertNotIn("coreedge/", self.read(path).lower())
		for path in (LOADER, BUNDLE):
			self.assertIn("window.edgesuiteui || window.edgeui", self.read(path).lower())
