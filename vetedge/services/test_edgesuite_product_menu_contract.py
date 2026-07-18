from pathlib import Path
import unittest


APP_ROOT = Path(__file__).resolve().parents[1]


class TestEdgeSuiteProductMenuContract(unittest.TestCase):
	def test_vetedge_prefers_standalone_edgesuite_ui_runtime(self):
		source = (APP_ROOT / "public/js/edgesuite_product_menu.js").read_text(encoding="utf-8")
		for expected in (
			"window.EdgeSuiteUI || window.EdgeUI",
			"edgeUI.registerProductMenu",
			"edgeUI.refreshProductMenu",
			"if (registerSharedMenu()) return",
			"MAX_RUNTIME_ATTEMPTS",
		):
			self.assertIn(expected, source)

	def test_icons_use_svg_markup_in_shared_and_fallback_paths(self):
		source = (APP_ROOT / "public/js/edgesuite_product_menu.js").read_text(encoding="utf-8")
		for expected in (
			"frappe.utils.icon",
			"vetedge-product-menu-waffle",
			'<svg viewBox="0 0 24 24"',
		):
			self.assertIn(expected, source)
		self.assertNotIn(">▦<", source)

	def test_fallback_waits_for_shared_runtime(self):
		source = (APP_ROOT / "public/js/edgesuite_product_menu.js").read_text(encoding="utf-8")
		mount_line = next(line.strip() for line in source.splitlines() if line.strip().startswith("function mount(attempt)"))
		self.assertLess(mount_line.index("registerSharedMenu()"), mount_line.index("mountFallback()"))
		self.assertIn("attempt < MAX_RUNTIME_ATTEMPTS", mount_line)


if __name__ == "__main__":
	unittest.main()
