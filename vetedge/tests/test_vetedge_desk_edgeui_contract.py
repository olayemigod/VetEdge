from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HOOKS = REPOSITORY_ROOT / "vetedge" / "hooks.py"
DESK_JS = REPOSITORY_ROOT / "vetedge" / "public" / "js" / "vetedge_desk_ui.js"
DESK_CSS = REPOSITORY_ROOT / "vetedge" / "public" / "css" / "vetedge_desk_ui.css"


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_vetedge_desk_edgeui_assets_are_loaded_after_the_shared_bridge():
	for path in (DESK_JS, DESK_CSS):
		assert path.exists(), path

	hooks = read(HOOKS)
	assert "vetedge_desk_ui.css?v=20260722-1" in hooks
	assert "vetedge_desk_ui.js?v=20260722-1" in hooks
	assert hooks.index("vetedge_professional_ui.css") < hooks.index("vetedge_desk_ui.css")
	assert hooks.index("vetedge_ui_bridge.js") < hooks.index("vetedge_desk_ui.js")


def test_vetedge_desk_adapter_targets_only_veterinary_module_list_and_forms():
	content = read(DESK_JS)
	for contract in (
		'!["List", "Form"].includes(view)',
		'String(meta.module || "") !== "Veterinary"',
		'meta.issingle || doctype === "Veterinary Settings"',
		'kind: isSettings ? "settings" : view === "List" ? "list" : "form"',
		"currentContext",
		"clearBodyContext",
	):
		assert contract in content


def test_vetedge_desk_adapter_covers_list_form_workflow_dialog_and_settings_surfaces():
	content = read(DESK_JS)
	for contract in (
		"enhanceList",
		"enhanceForm",
		"enhanceDialogs",
		"enhanceSettingsIntro",
		"vetedge-edge-list-row",
		"vetedge-edge-form-section",
		"vetedge-edge-workflow-action",
		"vetedge-edge-modal",
		"vetedge-edge-settings-intro",
		"MutationObserver",
		"page-change",
		"form-refresh",
		"list-rendered",
	):
		assert contract in content


def test_vetedge_navigation_keeps_native_doctype_routes_in_the_same_tab():
	content = read(DESK_JS)
	for contract in (
		"NATIVE_ROUTE_PREFIXES",
		'"/app/veterinary-"',
		'"/app/pet-"',
		'"/app/kennel"',
		"window.location.assign(route)",
		'edgeUI.registerAdapter("navigation:vetedge", adapter, { replace: true })',
		'edgeUI.registerAdapter("navigation:veterinary", adapter, { replace: true })',
	):
		assert contract in content


def test_vetedge_desk_adapter_is_presentation_only():
	content = read(DESK_JS)
	for forbidden in (
		"frappe.call(",
		"frappe.db.set_value",
		"frappe.client.set_value",
		"frappe.client.insert",
		"frappe.client.delete",
		"delete_doc",
		"doc.save",
		"doc.submit",
		"doc.cancel",
	):
		assert forbidden not in content


def test_vetedge_desk_css_is_scoped_and_reuses_edgesuite_tokens():
	content = read(DESK_CSS)
	for contract in (
		"body.vetedge-edge-desk",
		"body.vetedge-edge-list",
		"body.vetedge-edge-form",
		"body.vetedge-edge-settings",
		"--edge-primary",
		"--edge-color-surface",
		".vetedge-edge-list-row:hover",
		".vetedge-edge-form-section",
		".vetedge-edge-settings-intro",
		".vetedge-edge-modal .modal-content",
	):
		assert contract in content

	assert "body .form-section" not in content
