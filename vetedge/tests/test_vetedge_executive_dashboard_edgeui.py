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
SHARED_SHELL = REPOSITORY_ROOT / "vetedge" / "public" / "js" / "vetedge_shell" / "VetedgeEdgeSuiteShell.vue"
SHELL_STYLES = REPOSITORY_ROOT / "vetedge" / "public" / "css" / "dashboard_shell.css"
BADGE_STYLES = REPOSITORY_ROOT / "vetedge" / "public" / "css" / "veterinary_unread_badge.css"
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
TSCONFIG = REPOSITORY_ROOT / "tsconfig.json"


class TestVetedgeExecutiveDashboardEdgeUI(TestCase):
	def read(self, path):
		return path.read_text(encoding="utf-8")

	def test_page_config_and_assets_exist(self):
		config = json.loads(self.read(PAGE_CONFIG))
		self.assertEqual(config["name"], "vetedge-executive-dashboard")
		self.assertEqual(config["module"], "Veterinary")
		for path in (LOADER, BUNDLE, COMPONENT, PRODUCT_MENU, SHARED_SHELL, SERVER_API):
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
		self.assertIn("window.mountVetedgeExecutiveDashboard(root[0])", content)
		self.assertNotIn("runtime.createEdgeApp(window.VetedgeExecutiveDashboard)", content)
		self.assertNotIn("dashboard_shell.js", content)
		self.assertNotIn("coreedge", content.lower())

	def test_bundle_mounts_component_through_edgesuite_ui(self):
		content = self.read(BUNDLE)
		self.assertIn("window.EdgeSuiteUI || window.EdgeUI", content)
		self.assertIn("VetedgeExecutiveDashboard.components = { ...runtime.components, VetedgeEdgeSuiteShell }", content)
		self.assertIn("import VetedgeEdgeSuiteShell", content)
		self.assertIn("runtime.createEdgeApp(VetedgeExecutiveDashboard)", content)
		self.assertNotIn("import { createApp } from 'vue'", content)
		self.assertNotIn("coreedge", content.lower())


	def test_vue_build_resolves_without_coreedge_bridge(self):
		tsconfig = self.read(TSCONFIG)
		shell = self.read(SHARED_SHELL)
		bundle = self.read(BUNDLE)
		self.assertNotIn("coreedge", tsconfig.lower())
		self.assertNotIn("vue-bridge", tsconfig.lower())
		self.assertNotIn("@keydown.esc", shell)
		self.assertNotIn("@keyup.esc", shell)
		self.assertIn('@keydown="handleMenuKeydown"', shell)
		self.assertIn("handleMenuKeydown(event)", shell)
		self.assertIn("event.key === 'Escape'", shell)
		self.assertIn("event.preventDefault()", shell)
		self.assertIn("this.closeMenu()", shell)
		self.assertIn("window.EdgeSuiteUI || window.EdgeUI", bundle)

	def test_product_menu_and_notification_actions_are_present(self):
		component = self.read(COMPONENT)
		shell = self.read(SHARED_SHELL)
		product_menu = self.read(PRODUCT_MENU)
		self.assertIn("VetedgeEdgeSuiteShell", component)
		self.assertIn("EdgeNotificationBell", shell)
		self.assertIn("EdgeNotificationDrawer", shell)
		self.assertIn("notificationApi", component)
		self.assertIn("vetedge-suite-waffle-icon", shell)
		self.assertIn("wafflePoints", shell)
		self.assertLess(shell.index("vetedge-suite-icon-button"), shell.index('<div class="vetedge-suite-context"'))
		for contract in ("setInlineMode", "getSections", "navigate"):
			self.assertIn(contract, product_menu)
		self.assertNotIn("frappe.realtime", product_menu)

	def test_product_menu_is_global_idempotent_and_lifecycle_aware(self):
		product_menu = self.read(PRODUCT_MENU)
		hooks = self.read(HOOKS)
		self.assertIn("/assets/vetedge/js/edgesuite_product_menu.js", hooks)
		self.assertIn("removeDuplicates", product_menu)
		self.assertIn("already-mounted", product_menu)
		self.assertIn("toolbar_setup", product_menu)
		self.assertIn("page-change", product_menu)
		self.assertIn("desktop_screen", product_menu)
		self.assertIn("sidebar_setup", product_menu)
		self.assertIn("MutationObserver", product_menu)
		self.assertIn("function diagnose()", product_menu)
		self.assertIn("lastMountResult", product_menu)
		self.assertIn("currentMenuNodeCount", product_menu)
		self.assertIn("FALLBACK_ROUTES", product_menu)
		self.assertIn("configured_routes", product_menu)
		self.assertIn("vetedge-product-menu-slot--floating", product_menu)
		self.assertIn('"navbar-became-visible"', product_menu)
		self.assertIn('result(true, "inserted"', product_menu)
		self.assertIn('result(false, "no-navbar-target"', product_menu)
		self.assertNotIn("frappe.realtime", product_menu)
		self.assertNotIn("socket", product_menu.lower())

	def test_shared_shell_contract_is_present_on_both_reference_pages(self):
		executive = self.read(COMPONENT)
		stock = self.read(STOCK_COMPONENT)
		shell = self.read(SHARED_SHELL)
		for component in (executive, stock):
			self.assertIn("VetedgeEdgeSuiteShell", component)
			self.assertNotIn(':menuItems="menuItems"', component)
			self.assertNotIn("coreedge/", component.lower())
		for contract in (
			"vetedge-suite-context-bar",
			"vetedge-suite-context-leading",
			"EdgeNotificationBell",
			"EdgeNotificationDrawer",
			"setInlineMode?.(true)",
			"setInlineMode?.(false)",
			"Dashboards",
			"Veterinary Records",
			"Clinical Operations",
			"Billing & Payments",
			"Inventory & Pharmacy",
			"Reports",
			"Setup",
		):
			self.assertIn(contract, shell)
		self.assertNotIn("frappe.realtime", shell)

	def test_no_internal_navigation_and_empty_menu_uses_full_width(self):
		executive = self.read(COMPONENT)
		stock = self.read(STOCK_COMPONENT)
		styles = self.read(REPOSITORY_ROOT / "vetedge" / "public" / "css" / "dashboard_shell.css")
		self.assertNotIn(':menuItems="menuItems"', executive)
		self.assertNotIn(':menuItems="menuItems"', stock)
		self.assertIn(".vetedge-executive-dashboard-root .edge-sidebar", styles)
		self.assertIn(".vetedge-expiry-monitor-root .edge-sidebar", styles)
		self.assertIn("display: none !important", styles)
		self.assertIn("max-width: none", styles)

	def test_vetedge_theming_and_full_width_layout_contract(self):
		content = self.read(COMPONENT)
		shell = self.read(SHARED_SHELL)
		self.assertIn('data-edge-product="vetedge"', shell)
		self.assertIn('product="vetedge"', shell)
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
			"VetedgeEdgeSuiteShell",
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
		stock = self.read(STOCK_COMPONENT)
		self.assertIn("grid-template-columns: repeat(4, minmax(0, 1fr))", stock)
		self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", stock)
		self.assertIn("grid-template-columns: minmax(0, 1fr)", stock)
		self.assertIn("edge-select edge-control", content)
		self.assertIn("edge-input edge-control", content)
		self.assertIn("edge-button edge-button--primary", content)

	def test_fluid_shell_container_grid_and_chart_resize_contract(self):
		component = self.read(COMPONENT)
		styles = self.read(SHELL_STYLES)
		for contract in ("ResizeObserver", "resizeObserver?.disconnect()", "requestAnimationFrame", "chart?.resize?.()"):
			self.assertIn(contract, component)
		self.assertNotIn("display: grid !important", component)
		for contract in ("container-type: inline-size", "grid-template-columns: repeat(5", ":has(.vetedge-suite-shell)"):
			self.assertIn(contract, styles)

	def test_global_notification_badge_is_neutralized_for_edgesuite_pages(self):
		styles = self.read(BADGE_STYLES)
		self.assertIn("body:has(.vetedge-suite-shell)", styles)
		self.assertIn("#veterinary-unread-bell-badge", styles)
		self.assertIn("sidebar-collapsed", styles)

	def test_dashboard_content_is_preserved_inside_shared_shell(self):
		content = self.read(COMPONENT)
		shell = self.read(SHARED_SHELL)
		for contract in (
			"Veterinary performance",
			"Branch",
			"Period",
			"From Date",
			"To Date",
			"Apply / Refresh",
			'v-for="(card, index) in payload.kpis"',
			"payload.charts?.length",
			"new frappe.Chart",
			"renderChartTable",
			"payload.report_links?.length",
			"EdgeLoadingState",
			"EdgeEmptyState",
			"EdgeErrorState",
			"@retry=\"refresh\"",
		):
			self.assertIn(contract, content)
		self.assertIn("<slot />", shell)
		self.assertNotIn("v-if=\"$slots.default\"", shell)

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
		for path in (LOADER, BUNDLE, COMPONENT, PRODUCT_MENU, SHARED_SHELL):
			self.assertNotIn("coreedge/", self.read(path).lower())
