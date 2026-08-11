from pathlib import Path
from unittest import TestCase

REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE_BACKEND = REPO_ROOT / "vetedge" / "veterinary" / "page" / "stock_expiry_monitor" / "stock_expiry_monitor.py"
PAGE_LOADER = REPO_ROOT / "vetedge" / "veterinary" / "page" / "stock_expiry_monitor" / "stock_expiry_monitor.js"
BUNDLE = REPO_ROOT / "vetedge" / "public" / "js" / "vetedge_stock_expiry_monitor.bundle.js"


class TestVetEdgeStockExpiryFilterEfficiency(TestCase):
	def read(self, path: Path) -> str:
		return path.read_text(encoding="utf-8")

	def test_canonical_stock_expiry_filters_use_edgesuite_search_fields(self):
		bundle = self.read(BUNDLE)

		self.assertIn("EdgeLinkField", bundle)
		self.assertIn("searchWarehouses", bundle)
		self.assertIn("searchItemGroups", bundle)
		self.assertIn("'onUpdate:modelValue'", bundle)
		self.assertIn("page_length: 20", bundle)
		self.assertIn("FILTER_SEARCH_API", bundle)

	def test_canonical_stock_expiry_runtime_does_not_preload_filter_metadata(self):
		bundle = self.read(BUNDLE)

		self.assertNotIn("this.fetchMetadata();", bundle)
		self.assertNotIn("limit_page_length: 500", bundle)
		self.assertIn("this.metadataLoading = false", bundle)
		self.assertIn("Do not preload hundreds", bundle)

	def test_filter_search_backend_is_bounded_and_permission_aware(self):
		backend = self.read(PAGE_BACKEND)

		self.assertIn("FILTER_SEARCH_MAX_PAGE_LENGTH = 20", backend)
		self.assertIn("check_expiry_permissions()", backend)
		self.assertIn('frappe.has_permission(doctype, "read")', backend)
		self.assertIn("frappe.get_list(", backend)
		self.assertIn("page_length = min(max", backend)

	def test_selected_filter_values_are_revalidated_on_the_server(self):
		backend = self.read(PAGE_BACKEND)

		self.assertIn('_validate_reference_filter(filters, "warehouse")', backend)
		self.assertIn('_validate_reference_filter(filters, "item_group")', backend)
		self.assertIn('exact_filters["name"] = value', backend)
		self.assertIn("page_length=1", backend)

	def test_page_loader_requires_edgesuite_link_field(self):
		loader = self.read(PAGE_LOADER)

		self.assertIn("'EdgeLinkField'", loader)
