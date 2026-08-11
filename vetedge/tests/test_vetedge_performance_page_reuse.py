from pathlib import Path
from unittest import TestCase

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestVetEdgePerformancePageReuse(TestCase):
	def read(self, relative_path: str) -> str:
		return REPO_ROOT.joinpath(relative_path).read_text(encoding="utf-8")

	def test_resource_center_reuses_mounted_surface_before_dom_reset(self):
		loader = self.read("vetedge/veterinary/page/vetedge_resource_center/vetedge_resource_center.js")

		reuse_index = loader.index("if (wrapper.vue_app?.refresh)")
		reset_index = loader.index("$(page.body).empty()")
		self.assertLess(reuse_index, reset_index)
		self.assertIn("VETEDGE_RESOURCE_CENTER_REFRESH_MAX_AGE_MS = 15000", loader)
		self.assertIn("wrapper.vue_app.refresh({ maxAgeMs: VETEDGE_RESOURCE_CENTER_REFRESH_MAX_AGE_MS })", loader)

	def test_resource_center_bundle_exposes_stale_aware_refresh_contract(self):
		bundle = self.read("vetedge/public/js/vetedge_resource_center.bundle.js")

		self.assertIn("async refresh(options = {})", bundle)
		self.assertIn("Date.now() - lastRefreshAt < maxAgeMs", bundle)
		self.assertIn("applyRequestedState()", bundle)
		self.assertIn("openRequestedEditor(state)", bundle)
		self.assertIn("await resourceView.loadPage?.()", bundle)
		self.assertIn("lastRefreshAt = Date.now()", bundle)

	def test_stock_expiry_reuses_mounted_component_before_asset_loading(self):
		loader = self.read("vetedge/veterinary/page/stock_expiry_monitor/stock_expiry_monitor.js")

		reuse_index = loader.index("if (wrapper.vue_app && wrapper.vue_view)")
		reset_index = loader.index("$(page.body).empty()")
		self.assertLess(reuse_index, reset_index)
		self.assertIn("VETEDGE_STOCK_EXPIRY_REFRESH_MAX_AGE_MS = 15000", loader)
		self.assertIn("wrapper.vue_view.fetchData?.()", loader)
		self.assertIn("wrapper.vue_view.syncShellContext?.()", loader)
		self.assertIn("wrapper.vue_view = wrapper.vue_app.mount(root[0])", loader)
		self.assertIn("branchChanged || stale", loader)

	def test_stock_expiry_cold_metadata_is_not_reloaded_by_page_reuse_path(self):
		loader = self.read("vetedge/veterinary/page/stock_expiry_monitor/stock_expiry_monitor.js")
		component = self.read("vetedge/public/js/vetedge_stock_expiry_monitor/VetedgeStockExpiryMonitor.vue")

		# The current component still has cold-mount metadata queries. This slice
		# deliberately prevents repeated page remounts so these calls are not made
		# again merely because the user navigated away and back.
		self.assertIn("this.fetchMetadata();", component)
		self.assertIn("limit_page_length: 500", component)
		reuse_block = loader[
			loader.index("if (wrapper.vue_app && wrapper.vue_view)") : loader.index("$(page.body).empty()")
		]
		self.assertNotIn("frappe.require(", reuse_block)
		self.assertNotIn("unmount()", reuse_block)

	def test_executive_dashboard_reuses_branch_metadata_and_refreshes_payload_only_when_stale(self):
		loader = self.read("vetedge/veterinary/page/vetedge_executive_dashboard/vetedge_executive_dashboard.js")
		component = self.read("vetedge/public/js/vetedge_executive_dashboard/VetedgeExecutiveDashboard.vue")

		reuse_index = loader.index("if (wrapper.vue_app && wrapper.vue_view)")
		reset_index = loader.index("$(page.body).empty()")
		self.assertLess(reuse_index, reset_index)
		self.assertIn("VETEDGE_EXECUTIVE_REFRESH_MAX_AGE_MS = 15000", loader)
		self.assertIn("wrapper.vue_view.refresh?.()", loader)
		self.assertIn("wrapper.vue_view = wrapper.vue_app.mount(root[0])", loader)
		self.assertIn("limit_page_length: 500", component)

	def test_page_reuse_uses_no_background_polling(self):
		for relative_path in (
			"vetedge/veterinary/page/vetedge_resource_center/vetedge_resource_center.js",
			"vetedge/veterinary/page/stock_expiry_monitor/stock_expiry_monitor.js",
			"vetedge/veterinary/page/vetedge_executive_dashboard/vetedge_executive_dashboard.js",
		):
			self.assertNotIn("setInterval(", self.read(relative_path), relative_path)
