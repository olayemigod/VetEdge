from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"

MIGRATED_PAGES = {
	"settings": {
		"loader": APP / "veterinary/page/veterinary_settings_center/veterinary_settings_center.js",
		"page": APP / "veterinary/page/veterinary_settings_center/veterinary_settings_center.json",
		"bundle": APP / "public/js/veterinary_settings_center.bundle.js",
		"component": APP / "public/js/veterinary_settings_center/VeterinarySettingsCenter.vue",
		"provider": APP / "services/settings_page.py",
	},
	"masters": {
		"loader": APP / "veterinary/page/vetedge_master_workspace/vetedge_master_workspace.js",
		"page": APP / "veterinary/page/vetedge_master_workspace/vetedge_master_workspace.json",
		"bundle": APP / "public/js/vetedge_master_workspace.bundle.js",
		"component": APP / "public/js/vetedge_master_workspace/VetEdgeMasterWorkspace.vue",
		"provider": APP / "services/master_workspace.py",
	},
	"pricing": {
		"loader": APP / "veterinary/page/vetedge_pricing_master_workspace/vetedge_pricing_master_workspace.js",
		"page": APP / "veterinary/page/vetedge_pricing_master_workspace/vetedge_pricing_master_workspace.json",
		"bundle": APP / "public/js/vetedge_pricing_master_workspace.bundle.js",
		"component": APP / "public/js/vetedge_pricing_master_workspace/VetEdgePricingMasterWorkspace.vue",
		"provider": APP / "services/pricing_master_workspace.py",
	},
	"front_desk": {
		"loader": APP / "veterinary/page/vetedge_front_desk_action_center/vetedge_front_desk_action_center.js",
		"page": APP / "veterinary/page/vetedge_front_desk_action_center/vetedge_front_desk_action_center.json",
		"bundle": APP / "public/js/vetedge_front_desk_action_center.bundle.js",
		"component": APP / "public/js/vetedge_front_desk_action_center/VetEdgeFrontDeskActionCenter.vue",
		"provider": APP / "services/front_desk_action_center.py",
	},
	"clinical": {
		"loader": APP / "veterinary/page/vetedge_clinical_workspace/vetedge_clinical_workspace.js",
		"page": APP / "veterinary/page/vetedge_clinical_workspace/vetedge_clinical_workspace.json",
		"bundle": APP / "public/js/vetedge_clinical_workspace.bundle.js",
		"component": APP / "public/js/vetedge_clinical_workspace/VetEdgeClinicalWorkspace.vue",
		"provider": APP / "services/clinical_workspace.py",
	},
	"medical_history": {
		"loader": APP / "veterinary/page/veterinary_medical_history/veterinary_medical_history.js",
		"page": APP / "veterinary/page/veterinary_medical_history/veterinary_medical_history.json",
		"bundle": APP / "public/js/veterinary_medical_history.bundle.js",
		"component": APP / "public/js/veterinary_medical_history/VeterinaryMedicalHistory.vue",
		"provider": APP / "services/medical_history.py",
	},
	"service_operations": {
		"loader": APP / "veterinary/page/vetedge_service_operations/vetedge_service_operations.js",
		"page": APP / "veterinary/page/vetedge_service_operations/vetedge_service_operations.json",
		"bundle": APP / "public/js/vetedge_service_operations.bundle.js",
		"component": APP / "public/js/vetedge_service_operations/VetEdgeServiceOperations.vue",
		"provider": APP / "services/service_operations.py",
	},
}


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_recovered_edgesuite_pages_are_source_controlled_and_use_runtime_063():
	for name, paths in MIGRATED_PAGES.items():
		for kind, path in paths.items():
			assert path.exists(), f"{name} {kind} missing: {path}"
		loader = read(paths["loader"])
		component = read(paths["component"])
		bundle = read(paths["bundle"])
		assert "edgeui.bundle.js" in loader
		assert "edgesuite_ui.bundle.js" not in loader
		assert "window.EdgeSuiteUI || window.EdgeUI" in loader
		assert "0.6.3" in loader
		assert "EdgeAppShell" in component
		assert "runtime.components" in bundle
		assert "coreedge" not in component.lower()


def test_recovered_editing_surfaces_use_shared_edgesuite_form_controls():
	settings = read(MIGRATED_PAGES["settings"]["component"])
	masters = read(MIGRATED_PAGES["masters"]["component"])
	pricing = read(MIGRATED_PAGES["pricing"]["component"])
	front_desk = read(MIGRATED_PAGES["front_desk"]["component"])
	clinical = read(MIGRATED_PAGES["clinical"]["component"])
	medical_history = read(MIGRATED_PAGES["medical_history"]["component"])
	service_operations = read(MIGRATED_PAGES["service_operations"]["component"])

	for control in ("EdgeInput", "EdgeTextarea", "EdgeCheckbox", "EdgeDropdown", "EdgeLinkField"):
		assert control in settings
	for content in (masters, pricing):
		assert "EdgeDocumentForm" in content
		assert "EdgeWorkflowBar" in content
		assert "EdgeDropdown" in content
		assert "EdgeInput" in content
		assert "form-control" not in content
	for content in (front_desk, clinical):
		assert "EdgeModal" in content
		assert "EdgeDropdown" in content
		assert "EdgeInput" in content
		assert "EdgeTextarea" in content
		assert "frappe.ui.Dialog" not in content
		assert "form-control" not in content
	for contract in ("EdgeFilterBar", "EdgeLinkField", "EdgeInput", "EdgeDataTable"):
		assert contract in medical_history
	assert "form-control" not in medical_history
	assert "frappe.ui.Dialog" not in medical_history
	for contract in (
		"EdgeFilterBar", "EdgeLinkField", "EdgeInput", "EdgeDropdown", "EdgeTextarea",
		"EdgeDataTable", "EdgeModal",
	):
		assert contract in service_operations
	assert "frappe.ui.Dialog" not in service_operations
	assert "form-control" not in service_operations


def test_medical_history_preserves_page_and_rich_clinical_modal_contracts():
	component = read(MIGRATED_PAGES["medical_history"]["component"])
	provider = read(MIGRATED_PAGES["medical_history"]["provider"])
	clinical_bundle = read(MIGRATED_PAGES["clinical"]["bundle"])
	modal = read(APP / "public/js/vetedge_clinical_workspace/VetEdgeMedicalHistoryModal.vue")
	for contract in (
		"temperature",
		"weight",
		"heart_rate",
		"respiratory_rate",
		"Consultations",
		"Vitals",
		"Diagnoses",
		"Symptoms",
		"Treatments",
		"Vaccinations",
		"Laboratory",
		"new frappe.Chart",
		"get_patient_medical_history_view",
	):
		assert contract in component
		assert contract in modal
	assert '"treatment_plan_summary"' in provider
	assert "Treatment Plan Summary" in component
	assert "Treatment Plan Summary" in modal
	assert "stripHtml(row.treatment_plan_summary)" in component
	assert "stripHtml(row.treatment_plan_summary)" in modal
	assert "EdgeModal" in modal
	assert "VetEdgeMedicalHistoryModal" in clinical_bundle
	assert "historyView?.open?.({" in clinical_bundle
	assert "/app/veterinary-medical-history?patient=" not in clinical_bundle


def test_settings_brand_identity_is_restored_for_standalone_edgesuite_shell():
	identity = read(APP / "ui_identity.py")
	settings = read(APP / "veterinary/doctype/veterinary_settings/veterinary_settings.json")
	settings_client = read(APP / "veterinary/doctype/veterinary_settings/veterinary_settings.js")

	for contract in (
		"_settings_brand_identity",
		'"portal_brand_name"',
		'"portal_logo"',
		'settings_brand.get("name")',
		'settings_brand.get("logo")',
	):
		assert contract in identity
	assert '"fieldname": "portal_brand_name"' in settings
	assert '"fieldname": "portal_logo"' in settings
	assert "/desk/veterinary-settings-center" in settings_client
	assert "/app/veterinary-settings-center" not in settings_client


def test_recovered_page_and_deep_link_routes_point_to_migrated_workspaces():
	bridge = read(APP / "public/js/vetedge_ui_bridge.js")
	recovery = read(APP / "public/js/vetedge_navigation_recovery.js")
	home = read(APP / "veterinary/page/vetedge/vetedge.js")

	for route in (
		"/desk/veterinary-settings-center",
		"/desk/vetedge-master-workspace",
		"/desk/vetedge-pricing-master-workspace",
		"/desk/vetedge-front-desk-action-center",
		"/desk/vetedge-clinical-workspace",
		"/desk/veterinary-medical-history",
		"/desk/vetedge-service-operations",
	):
		assert route in bridge
	assert '"/desk/veterinary-consultation"' in bridge
	assert 'path === "/desk/veterinary-vital-signs"' in bridge
	assert "return openSameTab(route)" in bridge
	for contract in (
		'"/desk/kennel-availability-board": "availability"',
		'"/desk/pet-boarding-stay": "boarding-stays"',
		'"/desk/pet-boarding-care-record": "boarding-care-records"',
		'"/desk/pet-grooming-session": "grooming-sessions"',
	):
		assert contract in bridge
	for contract in (
		'"DocType:Veterinary Patient": "/desk/vetedge-resource-center?resource=patients"',
		'"DocType:Veterinary Consultation": "/desk/vetedge-clinical-workspace"',
		'"DocType:Pet Boarding Stay": "/desk/vetedge-service-operations?resource=boarding-stays"',
		'if (doctype === "Veterinary Vital Signs") return "";',
	):
		assert contract in recovery
	assert "/desk/vetedge-resource-center" in home

	guest_form = read(APP / "veterinary/doctype/veterinary_guest_booking_request/veterinary_guest_booking_request.js")
	guest_list = read(APP / "veterinary/doctype/veterinary_guest_booking_request/veterinary_guest_booking_request_list.js")
	missed_form = read(APP / "veterinary/doctype/veterinary_missed_appointment/veterinary_missed_appointment.js")
	missed_list = read(APP / "veterinary/doctype/veterinary_missed_appointment/veterinary_missed_appointment_list.js")
	queue = read(APP / "veterinary/page/veterinary_appointment_queue/veterinary_appointment_queue.js")
	for content in (guest_form, guest_list, missed_form, missed_list, queue):
		assert "/desk/vetedge-front-desk-action-center" in content
		assert "/app/vetedge-front-desk-action-center" not in content


def test_resource_center_publishes_frappe_v16_desk_full_form_routes():
	provider = read(APP / "services/resource_center.py")
	assert 'return f"/desk/{slug}/{name}" if name else f"/desk/{slug}"' in provider
	assert 'return f"/app/{slug}/{name}"' not in provider


def test_hospital_services_workspace_preserves_operational_actions_and_existing_service_authority():
	component = read(MIGRATED_PAGES["service_operations"]["component"])
	provider = read(MIGRATED_PAGES["service_operations"]["provider"])
	for contract in (
		"Kennel Availability",
		"Boarding Stays",
		"Care Records",
		"Grooming Sessions",
		"get_kennel_availability_board_view",
		"Add Care Record",
		"View Care Records",
		"Start Grooming",
		"Complete Grooming",
		"Cancel Session",
		"Billing / Payment",
	):
		assert contract in component or contract in provider
	assert "require_vetedge_platform_access" in provider
	assert "doc.insert()" in provider
	assert "transition_grooming_session_status" in provider
	assert "ignore_permissions=True" not in provider


def test_resource_center_deep_links_open_canonical_edgesuite_editor_or_appointment_flow():
	bundle = read(APP / "public/js/vetedge_resource_center.bundle.js")
	for contract in (
		"requestedName",
		"requestedNew",
		"quickEditorView?.open?.({",
		"resource: resourceView.resource",
		"flowView?.open?.()",
	):
		assert contract in bundle


def test_pricing_master_native_routes_are_redirected_to_edgesuite_workspace():
	mappings = {
		"veterinary_treatment_item": "treatment-items",
		"veterinary_treatment_type": "treatment-types",
		"veterinary_lab_test": "lab-tests",
		"veterinary_vaccine": "vaccines",
		"pet_grooming_service": "grooming-services",
	}
	for folder, resource in mappings.items():
		directory = APP / "veterinary/doctype" / folder
		for suffix in (".js", "_list.js"):
			path = directory / f"{folder}{suffix}"
			assert path.exists(), path
			content = read(path)
			assert "/desk/vetedge-pricing-master-workspace" in content
			assert "/app/vetedge-pricing-master-workspace" not in content
			assert f"resource={resource}" in content


def test_hospital_services_and_vital_signs_remain_while_obsolete_dashboard_stays_removed():
	dashboard_install = read(APP / "install/dashboard.py")
	sidebar = read(APP / "workspace_sidebar/vetedge.json")
	obsolete_page = APP / "veterinary/page/veterinary_hospitalisation_dashboard"
	assert not (obsolete_page / "veterinary_hospitalisation_dashboard.js").exists()
	assert not (obsolete_page / "veterinary_hospitalisation_dashboard.json").exists()
	assert "REMOVED_STANDARD_PAGES" in dashboard_install
	assert '"veterinary-hospitalisation-dashboard"' in dashboard_install
	assert '("Page", "veterinary-hospitalisation-dashboard")' in dashboard_install
	assert '("DocType", "Veterinary Vital Signs")' not in dashboard_install
	assert '"veterinary", "page", "veterinary_hospitalisation_dashboard"' not in dashboard_install
	assert '"label": "Vital Signs"' in sidebar
	assert '"link_to": "Veterinary Vital Signs"' in sidebar
	assert '"label": "Hospital & Services"' in sidebar


def test_clinical_workspace_safety_followups_are_restored_and_wired_into_ui():
	hooks = read(APP / "hooks.py")
	context = read(APP / "services/clinical_workspace_context.py")
	phase5 = read(APP / "services/clinical_workspace_phase5.py")
	stage3 = read(APP / "services/clinical_workspace_stage3.py")
	component = read(MIGRATED_PAGES["clinical"]["component"])

	assert "vetedge_navigation_recovery.js" in hooks
	assert "vetedge_clinical_route.js" not in hooks
	assert "enforce_consultation_practitioner_ownership" in hooks
	assert "enforce_pending_dispensary_completion_invariant" in hooks
	assert "enforce_vitals_consultation_ownership" in hooks
	assert "Doctors can only" in context
	assert "DISPENSARY_PENDING" in phase5
	assert "confirm_workspace_dispensary" in phase5
	assert "DEFAULT_CONSULTATION_SOURCE_DETAIL" in stage3
	assert "can_edit_default_consultation_billing_item" in stage3

	for contract in (
		"clinical_workspace_stage3.save_consultation",
		"clinical_workspace_context.get_clinical_context_options",
		"clinical_workspace_context.get_patient_owner_context",
		"clinical_workspace_stage3.get_default_consultation_fee_policy",
		"clinical_workspace_phase5.get_treatment_display_order",
		"clinical_workspace_phase5.get_dispensary_workspace_context",
		"clinical_workspace_phase5.confirm_workspace_dispensary",
		"Review Dispensary",
		"Confirm Dispensary Issue",
		"Pet Owner",
		"confirmDiscard()",
	):
		assert contract in component
	assert "window.confirm" not in component
	assert "frappe.ui.Dialog" not in component
