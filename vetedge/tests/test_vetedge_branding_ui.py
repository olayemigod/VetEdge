from __future__ import annotations

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


def test_branding_adapter_supplies_logo_upload_without_bypassing_document_save():
	content = read(BRANDING_UI)
	for contract in (
		"frappe?.ui?.FileUploader",
		'doctype: "Veterinary Settings"',
		'docname: "Veterinary Settings"',
		'allowed_file_types: ["image/*"]',
		"portal_logo",
		"Upload Logo",
		"Replace Logo",
		"Save Settings to keep the change",
		'edgeUI.registerComponent("EdgeDocumentForm"',
	):
		assert contract in content

	for unsafe in (
		"frappe.db.set_value",
		"frappe.client.set_value",
		"frappe.client.insert",
		"delete_file",
	):
		assert unsafe not in content


def test_shell_adapter_uses_boot_identity_and_refreshes_after_logo_change():
	content = read(BRANDING_UI)
	for contract in (
		'BRANDING_EVENT = "vetedge:branding-updated"',
		"edgesuite_ui_identity?.vetedge",
		"tenant_logo",
		"vetedge-shell-has-logo",
		"vetedge-shell-logo-mark",
		'edgeUI.registerComponent("EdgeAppShell"',
		"window.dispatchEvent(new CustomEvent",
	):
		assert contract in content


def test_boot_identity_prefers_saved_veterinary_settings_logo_then_safe_fallbacks():
	content = read(IDENTITY)
	for contract in (
		"def _settings_identity()",
		'frappe.get_single("Veterinary Settings")',
		'meta.has_field("portal_logo")',
		'tenant_logo = settings.get("logo") or company.get("logo") or branding.get("logo") or ""',
	):
		assert contract in content


def test_branding_adapter_is_a_global_desk_asset_before_the_ui_bridge():
	content = read(HOOKS)
	branding = '"/assets/vetedge/js/vetedge_branding_ui.js?v=20260723-3"'
	professional = '"/assets/vetedge/js/vetedge_professional_ui.js?v=20260719-1"'
	bridge = '"/assets/vetedge/js/vetedge_ui_bridge.js?v=20260720-2"'
	assert branding in content
	assert content.index(professional) < content.index(branding) < content.index(bridge)


def test_all_current_vetedge_edgesuite_pages_bound_branding_wait_and_mount_product_bundle():
	for loader in LOADERS:
		content = read(loader)
		assert "VetEdgeBrandingUI?.install?.()" in content, loader
		assert "brandingSettled" in content, loader
		assert "window.setTimeout" in content, loader
		assert "1500" in content, loader
		assert "vetedge_branding_ui.js?v=20260723-2" in content, loader
		install_index = content.index("VetEdgeBrandingUI?.install?.()")
		product_bundle_indexes = [
			content.find(bundle)
			for bundle in (
				"vetedge_document_workspace.bundle.js",
				"vetedge_resource_center.bundle.js",
				"vetedge_executive_dashboard.bundle.js",
				"vetedge_stock_expiry_monitor.bundle.js",
			)
			if content.find(bundle) >= 0
		]
		assert product_bundle_indexes
		assert install_index < product_bundle_indexes[0]
