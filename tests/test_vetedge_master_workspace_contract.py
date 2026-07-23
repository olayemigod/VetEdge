from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "vetedge" / "services" / "master_workspace.py"
COMPONENT = ROOT / "vetedge" / "public" / "js" / "vetedge_master_workspace" / "VetEdgeMasterWorkspace.vue"
BUNDLE = ROOT / "vetedge" / "public" / "js" / "vetedge_master_workspace.bundle.js"
SAFETY = ROOT / "vetedge" / "public" / "js" / "vetedge_workspace_safety.js"
BRIDGE = ROOT / "vetedge" / "public" / "js" / "vetedge_ui_bridge.js"
PROFESSIONAL = ROOT / "vetedge" / "public" / "js" / "vetedge_professional_ui.js"
HOME = ROOT / "vetedge" / "public" / "js" / "vetedge_home_navigation.js"
PROFESSIONAL_CSS = ROOT / "vetedge" / "public" / "css" / "vetedge_professional_ui.css"
HOOKS = ROOT / "vetedge" / "hooks.py"
PAGE_ROOT = ROOT / "vetedge" / "veterinary" / "page" / "vetedge_master_workspace"


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_phase_2a_master_scope_is_explicit_and_billing_safe():
	content = read(SERVICE)
	for resource, doctype in (
		("species", "Veterinary Species"),
		("breeds", "Veterinary Breed"),
		("symptoms", "Veterinary Symptom"),
		("diagnosis-categories", "Veterinary Diagnosis Category"),
		("diagnoses", "Veterinary Diagnosis"),
		("service-types", "Veterinary Service Type"),
		("consultation-types", "Consultation Type"),
	):
		assert f'"{resource}":' in content
		assert f'"doctype": "{doctype}"' in content

	for excluded in (
		"Veterinary Consultation",
		"Veterinary Lab Order",
		"Veterinary Vaccination Record",
		"Veterinary Hospitalisation",
		"Pet Grooming Appointment",
		"Pet Boarding Booking",
		"Sales Invoice",
		"Payment Entry",
	):
		assert f'"doctype": "{excluded}"' not in content


def test_master_service_preserves_permissions_platform_access_and_locking():
	content = read(SERVICE)
	for value in (
		"require_internal_user()",
		"frappe.has_permission",
		'doc.check_permission("write")',
		'doc.check_permission("delete")',
		"require_vetedge_platform_access",
		"frappe.TimestampMismatchError",
		"frappe.get_list",
		"frappe.delete_doc",
	):
		assert value in content


def test_master_relationships_are_filtered_and_validated_server_side():
	content = read(SERVICE)
	for value in (
		'"link_filters":',
		'"species":',
		'"category":',
		'"default_item":',
		'"disabled": 0',
		'"is_sales_item": 1',
		'_assert_active_link("Veterinary Species"',
		'_assert_active_link("Veterinary Diagnosis Category"',
		'"Default ERPNext Item must be an enabled sales item."',
		'"Standard Rate cannot be negative."',
		'"Sort Order cannot be negative."',
	):
		assert value in content


def test_master_page_is_full_edgesuite_and_not_native_form_styling():
	component = read(COMPONENT)
	for value in (
		"EdgeAppShell",
		"EdgePageLayout",
		"EdgePageHeader",
		"EdgeFilterBar",
		"EdgeDataTable",
		"EdgeDocumentForm",
		"EdgeWorkflowBar",
		"EdgeLinkField",
		"EdgeModal",
		"EdgeLoadingState",
		"EdgeEmptyState",
		"EdgeErrorState",
	):
		assert value in component
	assert "frappe.ui.form" not in component
	assert "cur_frm" not in component


def test_master_page_and_bundle_are_source_controlled():
	assert (PAGE_ROOT / "vetedge_master_workspace.json").exists()
	assert (PAGE_ROOT / "vetedge_master_workspace.js").exists()
	assert BUNDLE.exists()
	page = read(PAGE_ROOT / "vetedge_master_workspace.js")
	for value in (
		"edgesuite_ui.bundle.js",
		"vetedge_master_workspace.bundle.js",
		"Missing EdgeSuite UI master components",
		"window.VetEdgeBrandingUI?.install?.()",
	):
		assert value in page


def test_master_routes_replace_native_doctype_routes():
	bridge = read(BRIDGE)
	for path, resource in (
		("/app/veterinary-species", "species"),
		("/app/veterinary-breed", "breeds"),
		("/app/veterinary-symptom", "symptoms"),
		("/app/veterinary-diagnosis-category", "diagnosis-categories"),
		("/app/veterinary-diagnosis", "diagnoses"),
		("/app/veterinary-service-type", "service-types"),
		("/app/consultation-type", "consultation-types"),
	):
		assert f'"{path}": "{resource}"' in bridge
	assert '"/app/vetedge-master-workspace"' in bridge
	assert "migratedMasterTarget" in bridge


def test_veterinary_home_is_guaranteed_and_same_tab():
	home = read(HOME)
	for value in (
		'const HOME_ROUTE = "/app/vetedge"',
		'const HOME_LABEL = "Veterinary Home"',
		"ensureHomeLink",
		"installNavigationAdapter",
		"window.location.assign(HOME_ROUTE)",
		"navigationWrapped",
	):
		assert value in home
	assert "vetedge_home_navigation.js?v=20260723-1" in read(HOOKS)


def test_persistent_menu_is_compact_but_search_menu_has_short_descriptions():
	professional = read(PROFESSIONAL)
	for value in (
		"TECHNICAL_DESCRIPTIONS",
		"shortDescription",
		"compactShellGroups",
		'description: ""',
		"productMenuSections",
		'"Veterinary Home":',
		'description: "Return to the main workspace"',
		'window.frappe.require("edgesuite_ui.bundle.js"',
	):
		assert value in professional
	assert 'item.description || item.link_type' not in professional
	assert 'String(item.description || item.link_type' not in professional
	assert ".vetedge-product-menu-link-copy > small" in read(PROFESSIONAL_CSS)


def test_workspace_safety_is_shared_by_documents_and_masters():
	safety = read(SAFETY)
	document_bundle = read(ROOT / "vetedge" / "public" / "js" / "vetedge_document_workspace.bundle.js")
	master_bundle = read(BUNDLE)
	for value in (
		"beforeunload",
		"Discard unsaved changes?",
		"closeConfirmation(true)",
		"confirmPendingAction",
		"wrapGuardedMethod",
	):
		assert value in safety
	assert "applyWorkspaceSafety(VetEdgeDocumentWorkspace" in document_bundle
	assert "guardNavigation: true" in document_bundle
	assert "applyWorkspaceSafety(VetEdgeMasterWorkspace)" in master_bundle
