from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / "vetedge" / "hooks.py"
IDENTITY = ROOT / "vetedge" / "ui_identity.py"
BRIDGE = ROOT / "vetedge" / "public" / "js" / "vetedge_ui_bridge.js"
RESOURCE_API = ROOT / "vetedge" / "services" / "resource_center.py"
RESOURCE_LOADER = (
	ROOT
	/ "vetedge"
	/ "veterinary"
	/ "page"
	/ "vetedge_resource_center"
	/ "vetedge_resource_center.js"
)
RESOURCE_PAGE = RESOURCE_LOADER.with_suffix(".json")
RESOURCE_BUNDLE = ROOT / "vetedge" / "public" / "js" / "vetedge_resource_center.bundle.js"
RESOURCE_COMPONENT = (
	ROOT
	/ "vetedge"
	/ "public"
	/ "js"
	/ "vetedge_resource_center"
	/ "VetEdgeResourceCenter.vue"
)
APPOINTMENT_API = ROOT / "vetedge" / "services" / "appointment_edgeui.py"
APPOINTMENT_COMPONENT = (
	ROOT
	/ "vetedge"
	/ "public"
	/ "js"
	/ "vetedge_resource_center"
	/ "VetEdgeAppointmentFlow.vue"
)


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_boot_identity_separates_clinic_and_deployment_product_branding():
	content = read(IDENTITY)
	for contract in (
		"company_logo",
		"tenant_name",
		"tenant_logo",
		"get_edge_platform_mode()",
		'mode == "shared_hosted"',
		'product_name = "VetEdge" if is_saas else "Veterinary"',
		'product_icon": "stethoscope"',
		'bootinfo["edgesuite_ui_identity"]',
		'shared["vetedge"] = identity',
		'shared["veterinary"] = identity',
	):
		assert contract in content


def test_vetedge_registers_shared_notification_and_navigation_adapters():
	content = read(BRIDGE)
	for contract in (
		"supportsSharedContracts",
		"EdgeSuite UI 0.3 or newer",
		"notifications:vetedge",
		"notifications:veterinary",
		"navigation:vetedge",
		"navigation:veterinary",
		"get_my_veterinary_unread_bell_count",
		"get_my_notifications",
		"acknowledge_my_notification",
		"mark_my_notification_done",
		"dismiss_my_notification",
		"archive_my_notification",
		'window.open(route, "_blank", "noopener,noreferrer")',
		"/app/vetedge-resource-center?resource=",
	):
		assert contract in content


def test_api_driven_resources_stay_in_shell_and_other_desk_views_open_new_tab():
	content = read(BRIDGE)
	for route in (
		"/app/veterinary-patient",
		"/app/veterinary-appointment",
		"/app/veterinary-consultation",
		"/app/veterinary-lab-order",
		"/app/veterinary-vaccination-record",
	):
		assert route in content
	assert 'if (path.startsWith("/app/")) return openNewTab(route)' in content
	assert "PRODUCT_ROUTES.has(path)" in content
	assert '"/app/veterinary-settings-center"' in content
	assert "patchProductMenu" in content
	assert "menuItemRoute" in content
	assert "__vetedgeProductMenuNavigationPatched" in content
	assert "productMenuPatched" in content


def test_resource_center_uses_permission_aware_crud_and_protects_workflows():
	content = read(RESOURCE_API)
	for contract in (
		'frappe.has_permission(doctype, "read")',
		'frappe.has_permission(doctype, "create")',
		'frappe.has_permission(doctype, "write")',
		'frappe.has_permission(doctype, "delete")',
		'doc.check_permission("write")',
		'doc.check_permission("delete")',
		"doc.docstatus != 0",
		"_permission_aware_count",
		"frappe.get_list(",
		'"consultations":',
		'"allow_edit": False',
		'"lab-orders":',
		'"vaccinations":',
	):
		assert contract in content

	assert "frappe.db.count" not in content
	assert "doc.submit(" not in content
	assert "doc.cancel(" not in content
	assert "Sales Invoice" not in content
	assert "Payment Entry" not in content


def test_resource_center_count_uses_frappe_v16_aggregate_field_syntax():
	content = read(RESOURCE_API)
	assert 'fields=[{"COUNT": "*", "as": "total"}]' in content
	assert 'count(name) as total' not in content


def test_resource_center_page_uses_edgesuite_shell_and_full_form_new_tabs():
	for path in (RESOURCE_PAGE, RESOURCE_LOADER, RESOURCE_BUNDLE, RESOURCE_COMPONENT):
		assert path.exists(), path

	loader = read(RESOURCE_LOADER)
	component = read(RESOURCE_COMPONENT)
	assert "edgeui.bundle.js" in loader
	assert "vetedge_professional_ui.js" in loader
	assert "vetedge_resource_center.bundle.js" in loader
	assert loader.index("edgeui.bundle.js") < loader.index("vetedge_resource_center.bundle.js")
	assert "EdgeAppShell" in component
	assert "get_resource_page" in component
	assert "get_resource_editor" in component
	assert "save_resource_record" in component
	assert "delete_resource_record" in component
	assert '"_blank", "noopener,noreferrer"' in component
	assert "frappe.ui.Dialog" in component


def test_appointment_flow_uses_shared_links_and_server_safety():
	api = read(APPOINTMENT_API)
	component = read(APPOINTMENT_COMPONENT)
	bundle = read(RESOURCE_BUNDLE)
	loader = read(RESOURCE_LOADER)

	for contract in (
		"search_appointment_link",
		"create_appointment_owner",
		"create_appointment_patient",
		"create_edgeui_appointment",
		"frappe.get_list(",
		"get_assigned_branches",
		"get_veterinary_doctor_users",
		"can_access_branch_data",
		"validate_doctor_user",
	):
		assert contract in api
	assert "ignore_permissions" not in api
	assert "frappe.db.sql(" not in api
	assert "doc.submit(" not in api

	for contract in (
		"EdgeModal",
		"EdgeLinkField",
		"Create New Pet Owner",
		"Create New Veterinary Patient",
		"createOwnerForPatientFromQuery",
		"createPatientFromQuery",
		"patientCreateResolve",
		"ownerCreateResolve",
		"optionRecord(option)",
		"record.primary_owner",
		"this.clearPatient()",
		"this.clearPractitioner()",
		"create_edgeui_appointment",
	):
		assert contract in component

	assert component.index('label="Veterinary Patient"') < component.index("vetedge-appointment-flow-owner-summary")
	assert "frappe.ui.Dialog" not in component
	assert "window.open" not in component
	assert "VetEdgeAppointmentFlow" in bundle
	assert "flowApp.unmount()" in bundle
	assert "New Appointment" in bundle
	assert "interceptAppointmentAction" in bundle
	assert "EdgeLinkField" in loader
	assert "EdgeSuite UI 0.4.0 or newer" in loader


def test_hooks_load_menu_contract_bridge_and_identity_in_safe_order():
	content = read(HOOKS)
	assert "vetedge.ui_identity.extend_bootinfo" in content
	assert "vetedge_product_menu_config.js?v=20260721-1" in content
	assert "edgesuite_product_menu.js?v=20260721-1" in content
	assert "vetedge_ui_bridge.js?v=20260721-1" in content
	assert content.index("vetedge_product_menu_config.js") < content.index("edgesuite_product_menu.js")
	assert content.index("vetedge_professional_ui.js") < content.index("vetedge_ui_bridge.js")
