from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOADER = ROOT / "vetedge" / "veterinary" / "page" / "veterinary_settings_center" / "veterinary_settings_center.js"


def test_settings_mounts_from_page_show_after_professional_shell_install():
	content = LOADER.read_text(encoding="utf-8")

	for contract in (
		"function mountVeterinarySettings(wrapper)",
		'frappe.pages["veterinary-settings-center"].on_page_show',
		"window.VetEdgeProfessionalUI?.install?.()",
		"professional?.installed",
		'frappe.require("/assets/vetedge/js/vetedge_professional_ui.js", mountWithProfessionalShell)',
		"window.mountVeterinarySettingsCenter(root)",
		"if (wrapper.__veterinarySettingsApp?.view)",
		"refreshMountedVeterinarySettings(wrapper)",
	):
		assert contract in content

	install_index = content.index("window.VetEdgeProfessionalUI?.install?.()")
	mount_index = content.index("window.mountVeterinarySettingsCenter(root)")
	assert install_index < mount_index

	load_block = content.split('frappe.pages["veterinary-settings-center"].on_page_load', 1)[1].split(
		'frappe.pages["veterinary-settings-center"].on_page_show', 1
	)[0]
	assert "frappe.require(" not in load_block
	assert "setInterval(" not in content
