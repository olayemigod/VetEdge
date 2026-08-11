from pathlib import Path
from unittest import TestCase

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE = REPO_ROOT / "vetedge" / "public" / "js" / "vetedge_executive_dashboard.bundle.js"
COMPONENT = REPO_ROOT / "vetedge" / "public" / "js" / "vetedge_executive_dashboard" / "VetedgeExecutiveDashboard.vue"
SERVICE = REPO_ROOT / "vetedge" / "services" / "dashboard_filter_search.py"


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

	def test_no_background_polling_is_added(self):
		self.assertNotIn("setInterval(", self.read(BUNDLE))
