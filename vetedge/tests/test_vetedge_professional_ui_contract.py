from __future__ import annotations

from pathlib import Path
from unittest import TestCase

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HOOKS = REPOSITORY_ROOT / "vetedge" / "hooks.py"
PROFESSIONAL_JS = REPOSITORY_ROOT / "vetedge" / "public" / "js" / "vetedge_professional_ui.js"
NAVIGATION_RECOVERY_JS = REPOSITORY_ROOT / "vetedge" / "public" / "js" / "vetedge_navigation_recovery.js"
PROFESSIONAL_CSS = REPOSITORY_ROOT / "vetedge" / "public" / "css" / "vetedge_professional_ui.css"
NAVIGATION_COMPAT_CSS = REPOSITORY_ROOT / "vetedge" / "public" / "css" / "vetedge_navigation_shell_compat.css"
VETEDGE_HOME = REPOSITORY_ROOT / "vetedge" / "veterinary" / "page" / "vetedge" / "vetedge.js"
EXECUTIVE_LOADER = (
	REPOSITORY_ROOT
	/ "vetedge"
	/ "veterinary"
	/ "page"
	/ "vetedge_executive_dashboard"
	/ "vetedge_executive_dashboard.js"
)
STOCK_LOADER = (
	REPOSITORY_ROOT
	/ "vetedge"
	/ "veterinary"
	/ "page"
	/ "stock_expiry_monitor"
	/ "stock_expiry_monitor.js"
)


class TestVetEdgeProfessionalUIContract(TestCase):
	def read(self, path: Path) -> str:
		return path.read_text(encoding="utf-8")

	def test_professional_assets_are_loaded_after_existing_vetedge_shell_assets(self):
		for path in (PROFESSIONAL_JS, NAVIGATION_RECOVERY_JS, PROFESSIONAL_CSS, NAVIGATION_COMPAT_CSS):
			self.assertTrue(path.exists(), path)

		hooks = self.read(HOOKS)
		self.assertIn("vetedge_professional_ui.css?v=20260719-1", hooks)
		self.assertIn("vetedge_navigation_shell_compat.css?v=20260812-1", hooks)
		self.assertIn("vetedge_professional_ui.js?v=20260719-1", hooks)
		self.assertIn("vetedge_navigation_recovery.js?v=20260812-2", hooks)
		self.assertNotIn("vetedge_clinical_route.js", hooks)
		self.assertLess(hooks.index("dashboard_shell.css"), hooks.index("vetedge_professional_ui.css"))
		self.assertLess(hooks.index("vetedge_professional_ui.css"), hooks.index("vetedge_navigation_shell_compat.css"))
		self.assertLess(hooks.index("edgesuite_product_menu.js"), hooks.index("vetedge_professional_ui.js"))
		self.assertLess(hooks.index("vetedge_ui_bridge.js"), hooks.index("vetedge_navigation_recovery.js"))

	def test_consumer_adapter_uses_permission_filtered_workspace_navigation(self):
		content = self.read(PROFESSIONAL_JS)
		for contract in (
			"workspace_sidebar_item",
			"sidebars.vetedge || sidebars.veterinary",
			"source.hidden === 1",
			"source.type === \"Section Break\"",
			"source.type !== \"Link\"",
			"defaultCollapsed: Boolean(source.keep_closed)",
			"getMenuItems",
		):
			self.assertIn(contract, content)

	def test_consumer_adapter_uses_frappe_route_semantics_for_sidebar_links(self):
		content = self.read(PROFESSIONAL_JS)
		for contract in (
			"menuItemForRoute",
			"applyFrappeRoute",
			'window.frappe.set_route("query-report", item.link_to)',
			'window.frappe.set_route("List", item.link_to)',
			"window.frappe.set_route(item.link_to)",
			"window.frappe.set_route(...parts)",
		):
			self.assertIn(contract, content)
		self.assertNotIn("window.history.pushState", content)
		self.assertNotIn("Promise.resolve(router.route())", content)

	def test_canonical_navigation_recovery_restores_home_and_migrated_edgeui_routes(self):
		content = self.read(NAVIGATION_RECOVERY_JS)
		for contract in (
			'label: "Veterinary Home"',
			'route: "/desk/vetedge"',
			'"DocType:Veterinary Patient": "/desk/vetedge-resource-center?resource=patients"',
			'"DocType:Veterinary Appointment": "/desk/vetedge-resource-center?resource=appointments"',
			'"DocType:Veterinary Consultation": "/desk/vetedge-clinical-workspace"',
			'"Page:veterinary-appointment-queue": "/desk/vetedge-front-desk-action-center?tab=queue"',
			'"DocType:Veterinary Settings": "/desk/veterinary-settings-center"',
			'"DocType:Veterinary Species": "/desk/vetedge-master-workspace?resource=species"',
			'"DocType:Veterinary Treatment Item": "/desk/vetedge-pricing-master-workspace?resource=treatment-items"',
			'"DocType:Pet Boarding Stay": "/desk/vetedge-service-operations?resource=boarding-stays"',
			'edgeUI.registerComponent("EdgeAppShell", CanonicalVetEdgeShell, { replace: true })',
			"menuItems: groups",
			"onNavigate: (route) => applyDeskRoute(route)",
			"window.frappe.set_route(...parts)",
			"VetEdgeNavigationRecovery",
		):
			self.assertIn(contract, content)

		self.assertNotIn("coreedge/", content.lower())
		self.assertNotIn("window.history.pushState", content)

	def test_vetedge_home_stays_in_desk_and_routes_to_resource_center(self):
		content = self.read(VETEDGE_HOME)
		self.assertIn('title: __("Veterinary Home")', content)
		self.assertIn('const target = "/desk/vetedge-resource-center";', content)
		self.assertIn('frappe.set_route("vetedge-resource-center")', content)
		self.assertNotIn("window.location.replace", content)

	def test_consumer_adapter_installs_professional_shell_and_menu_contract(self):
		content = self.read(PROFESSIONAL_JS)
		for contract in (
			"window.EdgeSuiteUI || window.EdgeUI",
			"versionSupportsProfessionalUI",
			"edgeUI.components?.EdgeIcon",
			'edgeUI.registerComponent("EdgeAppShell", ProfessionalVetEdgeShell, { replace: true })',
			"hideNativeSidebar: attrs.hideNativeSidebar ?? true",
			"sectionStateKey: attrs.sectionStateKey || SECTION_STATE_KEY",
			"edgeUI.registerProductMenu",
			'menu_source: "vetedge-professional"',
			"edgeUI.refreshProductMenu",
			"MutationObserver",
			"VetEdgeProfessionalUI",
			"diagnose",
		):
			self.assertIn(contract, content)

		self.assertNotIn("coreedge/", content.lower())
		for forbidden in (
			"frappe.db.set_value",
			"frappe.client.set_value",
			"frappe.client.insert",
			"frappe.client.delete",
			"delete_doc",
		):
			self.assertNotIn(forbidden, content)

	def test_reference_page_loaders_require_edgeui_0_2_adapter_before_product_bundles(self):
		for loader, product_bundle, loader_function in (
			(EXECUTIVE_LOADER, "vetedge_executive_dashboard.bundle.js", "loadDashboard"),
			(STOCK_LOADER, "vetedge_stock_expiry_monitor.bundle.js", "loadMonitor"),
		):
			content = self.read(loader)
			self.assertIn("'EdgeIcon'", content)
			self.assertIn("/assets/vetedge/js/vetedge_professional_ui.js", content)
			self.assertIn("window.VetEdgeProfessionalUI?.install?.()", content)
			self.assertIn("if (window.VetEdgeProfessionalUI?.install)", content)
			self.assertIn(f"const {loader_function} = () =>", content)
			self.assertIn(
				f"frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', {loader_function})",
				content,
			)
			self.assertIn(f"\t\t\t{loader_function}();", content)
			self.assertIn(product_bundle, content)
			self.assertIn("EdgeSuite UI 0.2 or newer", content)
			self.assertLess(content.index("edgeui.bundle.js"), content.index(f"const {loader_function}"))
			self.assertNotIn(
				"frappe.require('/assets/vetedge/js/vetedge_professional_ui.js?v=",
				content,
			)
			self.assertNotIn("coreedge/", content.lower())

	def test_professional_css_restores_shared_sidebar_without_narrowing_page_content(self):
		content = self.read(PROFESSIONAL_CSS)
		for contract in (
			"body.edge-suite-product-vetedge",
			".edge-app-shell__sidebar.edge-sidebar",
			"display: flex !important",
			".edge-shell-body",
			".edge-shell-main",
			"flex: 1 1 auto !important",
			"width: auto !important",
			"max-width: none !important",
			"--edge-primary: #1769aa",
			"--edge-accent: #1f9d72",
			".vetedge-notification-icon svg",
		):
			self.assertIn(contract, content)

	def test_navigation_shell_v2_overrides_legacy_vetedge_menu_chrome_only(self):
		content = self.read(NAVIGATION_COMPAT_CSS)
		for contract in (
			"EdgeSuite Navigation Shell V2",
			".edge-app-shell.edge-nav-shell-v2 .edge-shell-body",
			"display: grid !important",
			"grid-template-columns: var(--edge-sidebar-width) minmax(0, 1fr) !important",
			".edge-sidebar-item.active",
			"var(--edge-color-brand-50)",
			"var(--edge-color-brand-600)",
			"var(--edge-color-surface)",
			'data-edge-appearance="dark"',
		):
			self.assertIn(contract, content)

		for forbidden in (
			"#1769aa",
			"#0f568f",
			"#1f9d72",
			"linear-gradient(90deg, var(--edge-primary-soft), var(--edge-accent-soft))",
		):
			self.assertNotIn(forbidden, content)

	def test_professional_css_reasserts_user_theme_after_legacy_shell_defaults(self):
		content = self.read(PROFESSIONAL_CSS)
		theme_section = content[content.index("/* EdgeSuite Theme System V1 compatibility.") :]
		for contract in (
			':root[data-edge-palette]',
			"--edge-primary: var(--edge-color-brand-600)",
			"--edge-primary-soft: var(--edge-color-brand-50)",
			"--edge-text: var(--edge-color-ink-950)",
			"--edge-text-muted: var(--edge-color-ink-500)",
			"--edge-surface: var(--edge-color-surface)",
			"--edge-bg: var(--edge-color-surface-muted)",
			".vetedge-executive-dashboard-root .edge-topbar",
			"color-mix(in srgb, var(--edge-color-surface) 94%, transparent)",
			".vetedge-product-menu-panel",
			".edge-alerts-container .alert-danger",
		):
			self.assertIn(contract, theme_section)

		for forbidden in (
			"--edge-surface: #fff",
			"--edge-bg: #f6f9fc",
			"--edge-text: #172033",
			"background: rgba(255, 255, 255, .94)",
		):
			self.assertNotIn(forbidden, theme_section)

	def test_executive_dashboard_theme_contract_covers_controls_cards_and_charts(self):
		content = self.read(PROFESSIONAL_CSS)
		qa_section = content[content.index("/* Executive Dashboard browser-QA fixes.") :]
		for contract in (
			".vetedge-executive-filter-grid .edge-control",
			"select.edge-control option",
			".vetedge-executive-section",
			".vetedge-executive-chart-card",
			".vetedge-executive-chart svg text",
			"fill: var(--edge-color-ink-500) !important",
			"stroke: var(--edge-color-border) !important",
			".graph-svg-tip",
			"background: var(--edge-color-surface)",
		):
			self.assertIn(contract, qa_section)
