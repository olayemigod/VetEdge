from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "vetedge" / "services" / "document_workspace.py"
PAGE_DIR = ROOT / "vetedge" / "veterinary" / "page" / "vetedge_document_workspace"
PAGE_JSON = PAGE_DIR / "vetedge_document_workspace.json"
PAGE_JS = PAGE_DIR / "vetedge_document_workspace.js"
BUNDLE = ROOT / "vetedge" / "public" / "js" / "vetedge_document_workspace.bundle.js"
COMPONENT_DIR = ROOT / "vetedge" / "public" / "js" / "vetedge_document_workspace"
COMPONENT = COMPONENT_DIR / "VetEdgeDocumentWorkspace.vue"
WORKSPACE_RUNTIME = COMPONENT_DIR / "workspace_runtime.js"
BRIDGE = ROOT / "vetedge" / "public" / "js" / "vetedge_ui_bridge.js"


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_first_full_document_batch_is_source_controlled_and_explicit():
	for path in (API, PAGE_JSON, PAGE_JS, BUNDLE, COMPONENT, WORKSPACE_RUNTIME):
		assert path.exists(), path

	content = read(API)
	for contract in (
		'"patients": {',
		'"appointments": {',
		'"settings": {',
		'"doctype": "Veterinary Patient"',
		'"doctype": "Veterinary Appointment"',
		'"doctype": "Veterinary Settings"',
	):
		assert contract in content

	for unapproved in (
		'"consultations": {',
		'"lab-orders": {',
		'"vaccinations": {',
		'"hospitalisations": {',
	):
		assert unapproved not in content


def test_workspace_backend_is_permission_branch_and_platform_safe():
	content = read(API)
	for contract in (
		"require_internal_user()",
		"frappe.has_permission",
		'doc.check_permission("read")',
		'doc.check_permission("write")',
		'doc.check_permission("delete")',
		"get_current_vetedge_branch",
		"frappe.get_list(",
		"require_vetedge_platform_access",
		"doc.insert()",
		"doc.save()",
		"frappe.delete_doc",
		"get_transitions(doc)",
		"transition_appointment_status",
		"create_consultation_from_appointment",
	):
		assert contract in content

	for unsafe in (
		"ignore_permissions=True",
		"frappe.db.set_value",
		"doc.submit()",
		"doc.cancel()",
		"Sales Invoice",
		"Payment Entry",
	):
		assert unsafe not in content


def test_workspace_generates_full_frappe_metadata_schema_including_settings_tables():
	content = read(API)
	for contract in (
		'LAYOUT_FIELDTYPES = {"Tab Break", "Section Break", "Column Break"}',
		"_build_form_schema",
		'field.fieldtype == "Tab Break"',
		'field.fieldtype == "Section Break"',
		'field.fieldtype == "Column Break"',
		'field.fieldtype == "Table"',
		'serialized["child_fields"]',
		'field["fieldtype"] == "Password"',
		"read_only_depends_on",
		"mandatory_depends_on",
	):
		assert contract in content


def test_page_requires_real_edgesuite_document_components_not_native_dialog_skinning():
	loader = read(PAGE_JS)
	component = read(COMPONENT)
	bundle = read(BUNDLE)

	for contract in (
		"EdgeDataTable",
		"EdgeDocumentForm",
		"EdgeWorkflowBar",
		"EdgeSettingsLayout",
		"EdgeModal",
		"EdgeLinkField",
		"EdgeSuite UI 0.5.0 or newer",
	):
		assert contract in loader or contract in component

	for contract in (
		"vetedge.services.document_workspace.get_document_list",
		"vetedge.services.document_workspace.get_document",
		"vetedge.services.document_workspace.save_document",
		"vetedge.services.document_workspace.apply_workflow_transition",
		"vetedge.services.document_workspace.perform_document_action",
		"frappe.desk.search.search_link",
	):
		assert contract in component

	assert "frappe.require('edgesuite_ui.bundle.js'" in loader
	assert "const runtime = window.EdgeSuiteUI;" in loader
	assert "frappe.require('edgeui.bundle.js'" not in loader
	assert "runtime.components" in bundle
	assert "installWorkspaceRuntime" in bundle
	assert "frappe.ui.Dialog" not in component
	assert "frappe.ui.Dialog" not in loader
	assert "frappe.client.insert" not in component
	assert "frappe.client.set_value" not in component


def test_confirmation_and_settings_navigation_lifecycle_is_safe():
	content = read(WORKSPACE_RUNTIME)
	for contract in (
		"installWorkspaceRuntime",
		"methods.closeConfirmation",
		"busy: false",
		"handler: null",
		'window.location.assign("/app/vetedge")',
		"component.__vetedgeWorkspaceRuntimeInstalled = true",
	):
		assert contract in content


def test_settings_use_grouped_edgesuite_layout_and_preserve_single_document_save():
	component = read(COMPONENT)
	api = read(API)
	for contract in (
		"EdgeSettingsLayout",
		"settingsGroups",
		"settingsVisibleSchema",
		"Save Settings",
		"definition.is_single",
	):
		assert contract in component
	assert 'doc = frappe.get_single(doctype)' in api
	assert '"is_single": True' in api


def test_navigation_routes_only_completed_resources_to_new_workspace():
	bridge = read(BRIDGE)
	for contract in (
		"DOCUMENT_ROUTES",
		'"/app/veterinary-patient": "patients"',
		'"/app/veterinary-appointment": "appointments"',
		'"/app/veterinary-settings": "settings"',
		"migratedTarget",
		"migratedDocumentTarget",
		'"/app/vetedge-document-workspace"',
		'?resource=${encodeURIComponent(resource)}',
		"documentRouteCount",
	):
		assert contract in bridge

	for legacy_contract in (
		'"/app/veterinary-consultation": "consultations"',
		'"/app/veterinary-lab-order": "lab-orders"',
		'"/app/veterinary-vaccination-record": "vaccinations"',
	):
		assert legacy_contract in bridge
