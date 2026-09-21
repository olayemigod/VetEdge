from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
VUE = APP_ROOT / "public" / "js" / "vetedge_stock_expiry_monitor" / "VetedgeStockExpiryMonitor.vue"
BUNDLE = APP_ROOT / "public" / "js" / "vetedge_stock_expiry_monitor.bundle.js"
PDF_PATCH = APP_ROOT / "public" / "js" / "report_pdf_patch.js"


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_stock_expiry_quantity_formatter_is_available_to_both_render_paths():
	vue = read(VUE)
	bundle = read(BUNDLE)

	assert "formatQty(value)" in vue
	assert "if (column?.fieldname === 'qty') return this.formatQty(value);" in vue
	assert "formatQty(value)" in bundle
	assert "this.formatQty(row.qty)" in bundle
	assert "this.formatQty(this.summary.affected_qty)" in bundle


def test_optional_raw_assets_supply_the_frappe_v16_loader_callback():
	patch = read(PDF_PATCH)

	assert "frappe.require(path, function vetedgeOptionalAssetLoaded() {})" in patch
