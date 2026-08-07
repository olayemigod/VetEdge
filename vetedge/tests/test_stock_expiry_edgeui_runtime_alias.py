from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
LOADER = APP_ROOT / "veterinary" / "page" / "stock_expiry_monitor" / "stock_expiry_monitor.js"
VUE = APP_ROOT / "public" / "js" / "vetedge_stock_expiry_monitor" / "VetedgeStockExpiryMonitor.vue"


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_stock_expiry_loader_aligns_shared_runtime_aliases_before_product_bundle():
	loader = read(LOADER)

	assert "return window.EdgeSuiteUI || window.EdgeUI || null;" in loader
	assert "if (!window.EdgeSuiteUI) window.EdgeSuiteUI = runtime;" in loader
	assert "if (!window.EdgeUI) window.EdgeUI = runtime;" in loader

	alias_position = loader.index("if (!window.EdgeUI) window.EdgeUI = runtime;")
	bundle_position = loader.index("frappe.require('vetedge_stock_expiry_monitor.bundle.js'")
	assert alias_position < bundle_position


def test_stock_expiry_stat_cards_are_runtime_components_not_missing_contracts():
	vue = read(VUE)

	assert "'EdgeStatCard'" in vue
	assert "runtimeComponents[name] || localEdgeUIComponents[name]" in vue
	assert "EdgeSuite UI failed to load" in vue
