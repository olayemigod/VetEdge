from pathlib import Path
from unittest import TestCase

from vetedge.tests.test_vetedge_executive_branch_efficiency import TestVetEdgeExecutiveBranchEfficiency
from vetedge.tests.test_vetedge_medical_history_lazy_loading import TestVetEdgeMedicalHistoryLazyLoading
from vetedge.tests.test_vetedge_stock_expiry_filter_efficiency import TestVetEdgeStockExpiryFilterEfficiency

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
		reuse_start = loader.index("if (wrapper.vue_app && wrapper.vue_view)")
		reuse_end = loader.index("// Backward-compatible cleanup", reuse_start)
		reuse_block = loader[reuse_start:reuse_end]
		self.assertNotIn("frappe.require(", reuse_block)
		self.assertNotIn("unmount()", reuse_block)
		self.assertIn("return;", reuse_block)

	def test_stock_expiry_branch_mapping_queries_only_relevant_warehouses(self):
		service = self.read("vetedge/services/stock_expiry_monitor.py")
		start = service.index("def _get_warehouse_branch_map")
		end = service.index("def _expiry_bucket_label", start)
		block = service[start:end]

		self.assertIn("mapping_fields = fields[1:]", block)
		self.assertIn('or_filters={fieldname: ["in", warehouses] for fieldname in mapping_fields}', block)
		self.assertNotIn('rows = frappe.get_all("Branch", fields=fields)', block)
		self.assertIn("for fieldname in mapping_fields:", block)

	def test_stock_expiry_interactive_path_paginates_in_database(self):
		page = self.read("vetedge/veterinary/page/stock_expiry_monitor/stock_expiry_monitor.py")
		service = self.read("vetedge/services/stock_expiry_interactive.py")

		self.assertIn("get_stock_expiry_interactive_data", page)
		self.assertNotIn("get_stock_expiry_rows", page)
		self.assertNotIn("all_rows =", page)
		self.assertNotIn("table_rows =", page)
		self.assertIn("LIMIT %(limit)s OFFSET %(offset)s", service)
		self.assertIn("SELECT COUNT(*) AS total_count", service)
		self.assertIn("FROM ({classified_sql}) classified", service)
		self.assertIn("MAX_INTERACTIVE_PAGE_LENGTH = 500", service)

	def test_stock_expiry_interactive_summary_aggregates_without_materializing_rows(self):
		service = self.read("vetedge/services/stock_expiry_interactive.py")

		for contract in (
			"AS expired_items",
			"AS expiring_soon",
			"AS affected_qty",
			"AS affected_warehouses",
			"AS highest_risk_items",
			"COUNT(",
			"DISTINCT CASE",
			"SUM(",
		):
			self.assertIn(contract, service)
		self.assertIn("CASE WHEN expiry_date IS NULL THEN 1 ELSE 0 END ASC", service)
		self.assertIn("DATEDIFF(expiry_date, %(today)s) AS days_to_expiry", service)

	def test_stock_expiry_interactive_query_preserves_operational_filters(self):
		service = self.read("vetedge/services/stock_expiry_interactive.py")

		for contract in (
			'w.company = %(company)s',
			'sle.warehouse = %(warehouse)s',
			'i.item_group = %(item_group)s',
			'b.item = %(item)s',
			'sle.warehouse = %(branch_warehouse)s',
			'get_branch_dispensary_warehouse(',
			'HAVING qty > 0',
		):
			self.assertIn(contract, service)
		self.assertIn("get_stock_expiry_rows()", service)
		self.assertIn("remains the full-dataset contract", service)

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

	def test_vaccination_scheduler_filters_dates_before_reading_rows(self):
		service = self.read("vetedge/services/vaccination_notifications.py")

		self.assertIn('"next_due_date": ["between", [today, add_days(today, due_soon_days)]]', service)
		self.assertIn('"next_due_date": ["<", today]', service)
		self.assertNotIn('frappe.db.get_value("Veterinary Patient", row.get("patient"), "status")', service)

	def test_vaccination_scheduler_pages_rows_and_bulk_loads_patient_status(self):
		service = self.read("vetedge/services/vaccination_notifications.py")

		self.assertIn("VACCINATION_NOTIFICATION_PAGE_LENGTH = 100", service)
		self.assertIn("start=start", service)
		self.assertIn("limit_page_length=page_length", service)
		self.assertIn('filters={"name": ["in", patient_names]}', service)
		self.assertIn('fields=["name", "status"]', service)
		self.assertIn("start += len(rows)", service)
		self.assertIn("return min(max(value, 1), VACCINATION_NOTIFICATION_PAGE_LENGTH)", service)

	def test_page_reuse_uses_no_background_polling(self):
		for relative_path in (
			"vetedge/veterinary/page/vetedge_resource_center/vetedge_resource_center.js",
			"vetedge/veterinary/page/stock_expiry_monitor/stock_expiry_monitor.js",
			"vetedge/veterinary/page/vetedge_executive_dashboard/vetedge_executive_dashboard.js",
		):
			self.assertNotIn("setInterval(", self.read(relative_path), relative_path)


# Imported TestCase classes are intentionally exposed in this module so the
# existing Fast Validation entrypoint executes all performance/data-efficiency
# contracts together on the consolidated QA branch.
PERFORMANCE_SUITES = (
	TestVetEdgeExecutiveBranchEfficiency,
	TestVetEdgeMedicalHistoryLazyLoading,
	TestVetEdgeStockExpiryFilterEfficiency,
)
