from pathlib import Path
from unittest import TestCase

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE = REPO_ROOT / "vetedge" / "public" / "js" / "vetedge_executive_dashboard.bundle.js"
COMPONENT = REPO_ROOT / "vetedge" / "public" / "js" / "vetedge_executive_dashboard" / "VetedgeExecutiveDashboard.vue"
SERVICE = REPO_ROOT / "vetedge" / "services" / "dashboard_filter_search.py"
OPTIMIZED = REPO_ROOT / "vetedge" / "services" / "executive_dashboard_optimized.py"
FINANCIAL_METRICS = REPO_ROOT / "vetedge" / "services" / "executive_financial_metrics.py"
SHARED_HOST_PAYLOAD = REPO_ROOT / "vetedge" / "services" / "dashboard_host_payload.py"
HOOKS = REPO_ROOT / "vetedge" / "hooks.py"


class TestVetEdgeExecutiveBranchEfficiency(TestCase):
	def read(self, path: Path) -> str:
		return path.read_text(encoding="utf-8")

	def test_canonical_bundle_uses_bounded_branch_search(self):
		bundle = self.read(BUNDLE)

		self.assertIn("EdgeLinkField", bundle)
		self.assertIn("BRANCH_SEARCH_PAGE_LENGTH = 20", bundle)
		self.assertIn("search_dashboard_branches", bundle)
		self.assertIn("page_length: BRANCH_SEARCH_PAGE_LENGTH", bundle)
		self.assertIn("selectedLabel: this.value || 'All Branches'", bundle)

	def test_canonical_mount_skips_legacy_500_branch_preload(self):
		bundle = self.read(BUNDLE)
		component = self.read(COMPONENT)

		self.assertIn("limit_page_length: 500", component)
		mounted_start = bundle.index("VetedgeExecutiveDashboard.mounted = function mountedLowDataDashboard")
		mounted_end = bundle.index(
			"VetedgeExecutiveDashboard.beforeUnmount = function beforeUnmountLowDataDashboard",
			mounted_start,
		)
		mounted = bundle[mounted_start:mounted_end]
		self.assertNotIn("loadBranches", mounted)
		self.assertIn("this.fetchNotifications()", mounted)
		self.assertIn("this.refresh()", mounted)

	def test_dashboard_payload_uses_server_validated_branch_wrapper(self):
		bundle = self.read(BUNDLE)
		service = self.read(SERVICE)

		self.assertIn("get_executive_dashboard_payload", bundle)
		self.assertIn("validate_dashboard_branch_selection", service)
		self.assertIn('validate_dashboard_access("executive")', service)
		self.assertIn("normalize_dashboard_filters(", service)
		self.assertIn('get_dashboard_payload("executive", payload_filters)', service)

	def test_branch_search_is_permission_aware_and_hard_capped(self):
		service = self.read(SERVICE)

		self.assertIn("DASHBOARD_BRANCH_SEARCH_MAX_PAGE_LENGTH = 20", service)
		self.assertIn("user_has_global_branch_access", service)
		self.assertIn("get_assigned_branches", service)
		self.assertIn('frappe.has_permission("Branch", "read")', service)
		self.assertIn("frappe.get_list(", service)
		self.assertIn("page_length = min(", service)
		self.assertNotIn("ignore_permissions", service)

	def test_branch_scope_matches_existing_dashboard_visibility_policy(self):
		service = self.read(SERVICE)

		self.assertIn("BRANCH_SCOPED_ROLES", service)
		self.assertIn("get_user_roles(user) & BRANCH_SCOPED_ROLES", service)
		self.assertIn("def _explicit_branch_scope", service)
		self.assertIn("if explicit_scope:", service)
		self.assertNotIn("if not assigned:", service)

	def test_executive_unpaid_kpi_uses_lightweight_count_path(self):
		optimized = self.read(OPTIMIZED)
		metrics = self.read(FINANCIAL_METRICS)

		self.assertIn("count_executive_unpaid_invoices", optimized)
		self.assertIn("unpaid_count = count_executive_unpaid_invoices(filters)", optimized)
		self.assertIn('_kpi(_("Unpaid Invoices"), unpaid_count)', optimized)
		self.assertNotIn('unpaid_rows = _rows("Unpaid Invoice Report", filters)', optimized)
		self.assertIn("def count_executive_unpaid_invoices", metrics)
		self.assertNotIn("build_financial_dataset", metrics)
		self.assertNotIn("_get_patient_title_map", metrics)

	def test_executive_unpaid_count_preserves_branch_and_report_filter_truth(self):
		metrics = self.read(FINANCIAL_METRICS)

		self.assertIn("_get_sales_invoice_rows(filters, unpaid_only=not draft_mode)", metrics)
		self.assertIn('docstatus_value in (0, "0")', metrics)
		self.assertNotIn('cint(filters.get("docstatus")) == 0', metrics)
		self.assertIn('flt(row.get("outstanding_amount")) > 0', metrics)
		self.assertIn("_build_invoice_context_map(invoice_names)", metrics)
		self.assertIn("_resolve_invoice_report_branch", metrics)
		self.assertIn('branch = cstr(filters.get("branch") or "").strip()', metrics)
		self.assertIn("if not branch or not invoices:", metrics)
		for age_range in ("0-30", "31-60", "61-90", "90+"):
			self.assertIn(f'age_range == "{age_range}"', metrics)

	def test_shared_v5_rpc_routes_through_optimized_dashboard_host_adapter(self):
		hooks = self.read(HOOKS)
		adapter = self.read(SHARED_HOST_PAYLOAD)

		self.assertIn(
			'"vetedge.services.reporting_logic_v5.get_dashboard_payload": "vetedge.services.dashboard_host_payload.get_dashboard_payload"',
			hooks,
		)
		for contract in (
			'if key == "executive":',
			"return _executive_payload(normalized)",
			'if key == "clinical":',
			"return _clinical_payload(normalized)",
			'if key == "lab":',
			"return _lab_payload(normalized)",
			'if key == "vaccination":',
			"return _vaccination_payload(normalized)",
			'if key in {"branch_performance", "practitioner_performance"}:',
			"return v5.get_dashboard_payload(key, normalized)",
			"validate_dashboard_access(key)",
			"normalize_dashboard_filters(key, v4._to_dict(filters))",
		):
			self.assertIn(contract, adapter)

	def test_shared_executive_preserves_v5_range_semantics_without_unpaid_report_rows(self):
		adapter = self.read(SHARED_HOST_PAYLOAD)

		self.assertIn("unpaid_count = count_executive_unpaid_invoices(filters)", adapter)
		self.assertNotIn('v4._rows("Unpaid Invoice Report", filters)', adapter)
		for label in (
			"Consultations in Range",
			"Revenue in Range",
			"Unpaid Invoices in Range",
			"Appointments in Range",
			"Active Patients (Current)",
		):
			self.assertIn(label, adapter)
		self.assertIn('"from_date": filters.get("from_date")', adapter)
		self.assertIn('"to_date": filters.get("to_date")', adapter)
		self.assertIn('"branch": filters.get("branch")', adapter)

	def test_no_background_polling_is_added(self):
		self.assertNotIn("setInterval(", self.read(BUNDLE))
