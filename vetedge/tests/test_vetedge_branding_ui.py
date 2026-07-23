from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRANDING_UI = ROOT / "vetedge" / "public" / "js" / "vetedge_branding_ui.js"
IDENTITY = ROOT / "vetedge" / "ui_identity.py"
HOOKS = ROOT / "vetedge" / "hooks.py"
LOADERS = (
	ROOT / "vetedge" / "veterinary" / "page" / "vetedge_document_workspace" / "vetedge_document_workspace.js",
	ROOT / "vetedge" / "veterinary" / "page" / "vetedge_resource_center" / "vetedge_resource_center.js",
	ROOT / "vetedge" / "veterinary" / "page" / "vetedge_executive_dashboard" / "vetedge_executive_dashboard.js",
	ROOT / "vetedge" / "veterinary" / "page" / "stock_expiry_monitor" / "stock_expiry_monitor.js",
)


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_owner_logo_upload_is_portal_scoped():
	content = read(BRANDING_UI)
	for value in (
		"FileUploader",
		"Veterinary Settings",
		"portal_logo",
		"Owner Portal Logo",
		"portal_branding_tab",
		"withoutPortalLogoField",
		"does not change the VetEdge operational shell",
		"Save Settings to keep the change",
	):
		assert value in content
	assert "updateBootIdentityLogo" not in content


def test_shell_uses_product_logo_and_generic_veterinary_fallback():
	content = read(BRANDING_UI)
	for value in (
		'identity.product_logo || ""',
		"vetedge-shell-has-product-logo",
		"vetedge-shell-generic-product",
		"vetedge-shell-product-logo-mark",
		"vetedge-shell-generic-mark",
		'identity.product_icon || "stethoscope"',
	):
		assert value in content
	assert "tenant_logo || bootIdentity().product_logo" not in content


def test_identity_separates_owner_and_coreedge_product_logos():
	content = read(IDENTITY)
	for value in (
		"_owner_portal_identity",
		"COREDGE_PRODUCT_LOGO_KEYS",
		"product_logo_url",
		"product_app_logo_url",
		"app_logo_url",
		'_coreedge_product_logo_url(mode: str)',
		'if mode != "shared_hosted"',
		'"owner_portal_logo": owner_portal_logo',
		'"product_logo_source": "coreedge" if product_logo else "generic"',
		'"product_logo_scope": "operational_shell"',
	):
		assert value in content


def test_branding_asset_is_global_and_cannot_block_pages():
	hooks = read(HOOKS)
	assert "vetedge_branding_ui.js?v=20260723-4" in hooks
	for loader in LOADERS:
		content = read(loader)
		assert "VetEdgeBrandingUI?.install?.()" in content
		assert "brandingSettled" in content
		assert "window.setTimeout" in content
		assert "1500" in content
