from __future__ import annotations

from pathlib import Path
from unittest import TestCase

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HOOKS = REPOSITORY_ROOT / "vetedge" / "hooks.py"
PROFESSIONAL_JS = REPOSITORY_ROOT / "vetedge" / "public" / "js" / "vetedge_professional_ui.js"
PROFESSIONAL_CSS = REPOSITORY_ROOT / "vetedge" / "public" / "css" / "vetedge_professional_ui.css"
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
		for path in (PROFESSIONAL_JS, PROFESSIONAL_CSS):
			self.assertTrue(path.exists(), path)

		hooks = self.read(HOOKS)
		self.assertIn("vetedge_professional_ui.css?v=20260719-1", hooks)
		self.assertIn("vetedge_professional_ui.js?v=20260719-1", hooks)
		self.assertLess(hooks.index("dashboard_shell.css"), hooks.index("vetedge_professional_ui.css"))
		self.assertLess(hooks.index("edgesuite_product_menu.js"), hooks.index("vetedge_professional_ui.js"))

	def test_consumer_adapter_uses_permission_filtered_workspace_navigation(self):
		content = self.read(PROFESSIONAL_JS)
		for contract in (
			"workspace_sidebar_item",
			"sidebars.veterinary || sidebars.vetedge",
			"source.hidden === 1",
			"source.type === \"Section Break\"",
			"source.type !== \"Link\"",
			"defaultCollapsed: Boolean(source.keep_closed)",
			"getMenuItems",
		):
			self.assertIn(contract, content)

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
		for loader, product_bundle in (
			(EXECUTIVE_LOADER, "vetedge_executive_dashboard.bundle.js"),
			(STOCK_LOADER, "vetedge_stock_expiry_monitor.bundle.js"),
		):
			content = self.read(loader)
			self.assertIn("'EdgeIcon'", content)
			self.assertIn("vetedge_professional_ui.js?v=20260719-1", content)
			self.assertIn("window.VetEdgeProfessionalUI?.install?.()", content)
			self.assertIn("EdgeSuite UI 0.2 or newer", content)
			self.assertLess(content.index("edgeui.bundle.js"), content.index("vetedge_professional_ui.js"))
			self.assertLess(content.index("vetedge_professional_ui.js"), content.index(product_bundle))
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
