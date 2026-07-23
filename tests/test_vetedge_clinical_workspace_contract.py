from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "vetedge" / "services" / "clinical_workspace.py"
COMPONENT = (
	ROOT
	/ "vetedge"
	/ "public"
	/ "js"
	/ "vetedge_clinical_workspace"
	/ "VetEdgeClinicalWorkspace.vue"
)
BUNDLE = ROOT / "vetedge" / "public" / "js" / "vetedge_clinical_workspace.bundle.js"
ROUTE = ROOT / "vetedge" / "public" / "js" / "vetedge_clinical_route.js"
LIST = (
	ROOT
	/ "vetedge"
	/ "veterinary"
	/ "doctype"
	/ "veterinary_consultation"
	/ "veterinary_consultation_list.js"
)
PAGE_ROOT = ROOT / "vetedge" / "veterinary" / "page" / "vetedge_clinical_workspace"
HOME_PAGE_ROOT = ROOT / "vetedge" / "veterinary" / "page" / "vetedge"
HOOKS = ROOT / "vetedge" / "hooks.py"
HOME_NAVIGATION = ROOT / "vetedge" / "public" / "js" / "vetedge_home_navigation.js"


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_phase_4a_uses_a_dedicated_clinical_provider():
	service = read(SERVICE)
	for contract in (
		"def get_clinical_summary",
		"def get_consultations",
		"def get_consultation_detail",
		"def save_consultation",
		"def perform_consultation_action",
		"def create_consultation_vitals",
		"def get_consultation_history",
		"def get_clinical_link_options",
	):
		assert contract in service

	assert "document_workspace" not in service
	assert "master_workspace" not in service
	assert 'frappe.get_doc("Sales Invoice"' not in service
	assert 'frappe.get_doc("Payment Entry"' not in service
	assert 'frappe.get_doc("Stock Entry"' not in service
	assert "doc.submit()" not in service
	assert "doc.cancel()" not in service


def test_clinical_reads_and_writes_preserve_frappe_permissions_and_branch_safety():
	service = read(SERVICE)
	for contract in (
		"require_internal_user()",
		"frappe.get_list(",
		'doc.check_permission("read")',
		'doc.check_permission("write")',
		"frappe.has_permission(",
		"can_access_consultation",
		"can_access_branch_data",
		"get_assigned_branches",
		"user_has_global_branch_access",
		"require_vetedge_platform_access",
		"frappe.TimestampMismatchError",
		"doc.insert()",
		"doc.save()",
	):
		assert contract in service
	assert "ignore_permissions=True" not in service
	assert "frappe.get_all(" not in service
	assert "frappe.db.set_value" not in service


def test_status_vitals_history_and_treatment_defaults_delegate_to_existing_services():
	service = read(SERVICE)
	for contract in (
		"transition_consultation_status(name, target)",
		"create_vitals_from_consultation(name, values)",
		"get_latest_vitals_for_consultation(doc.name)",
		"get_patient_medical_history_view",
		"get_treatment_item_defaults_for_consultation",
		"get_treatment_item_link_options",
		'is_enabled("vitals")',
	):
		assert contract in service


def test_billed_and_source_generated_treatment_rows_are_not_silently_rewritten():
	service = read(SERVICE)
	component = read(COMPONENT)
	bundle = read(BUNDLE)
	for contract in (
		"PLANNED_TREATMENT_IMMUTABLE_FIELDS",
		"PROTECTED_TREATMENT_SOURCE_TYPES",
		"Source-generated or billed treatment row",
		"cannot be removed",
		"cannot be edited",
		'row["source_type"] = "Treatment"',
		"CONSULTATION_SCOPE_LOCKED_STATUSES",
		"detail.scope_locked",
		"treatmentRowLocked(row)",
		"treatmentRowLockedWithSourceProtection",
	):
		assert contract in service or contract in component or contract in bundle


def test_frontend_is_full_edgesuite_clinical_workspace():
	for path in (
		SERVICE,
		COMPONENT,
		BUNDLE,
		ROUTE,
		PAGE_ROOT / "vetedge_clinical_workspace.js",
		PAGE_ROOT / "vetedge_clinical_workspace.json",
	):
		assert path.exists(), path

	component = read(COMPONENT)
	loader = read(PAGE_ROOT / "vetedge_clinical_workspace.js")
	bundle = read(BUNDLE)
	for contract in (
		"EdgeAppShell",
		"EdgePageLayout",
		"EdgePageHeader",
		"EdgeStatCard",
		"EdgeFilterBar",
		"EdgeDataTable",
		"EdgeStatusBadge",
		"EdgeLinkField",
		"EdgeModal",
		"EdgeLoadingState",
		"EdgeErrorState",
		"Clinical Findings",
		"Treatment Plan",
		"Vitals & Billing",
	):
		assert contract in component

	assert "frappe.ui.form" not in component
	assert "cur_frm" not in component
	assert "frappe.require('edgesuite_ui.bundle.js'" in loader
	assert "const runtime = window.EdgeSuiteUI;" in loader
	assert "'EdgeIcon'" in loader
	assert "resetPageScroll" in loader
	assert "frappe.require('edgeui.bundle.js'" not in loader
	assert "const runtime = window.EdgeSuiteUI;" in bundle
	assert "window.EdgeUI" not in bundle
	assert "applyWorkspaceSafety(VetEdgeClinicalWorkspace, { guardNavigation: true })" in bundle
	assert "saveVitalsWithReliableClose" in bundle


def test_manual_qa_regressions_render_real_rows_and_icons():
	bundle = read(BUNDLE)
	for contract in (
		"fieldname: column.fieldname || column.key",
		"status: column.status === true || column.type === 'status'",
		"VetEdgeClinicalStatCard",
		"runtime?.components?.EdgeIcon",
		"CLINICAL_ICON_ALIASES",
	):
		assert contract in bundle


def test_native_consultation_routes_resolve_to_the_clinical_workspace():
	route = read(ROUTE)
	list_script = read(LIST)
	hooks = read(HOOKS)
	for contract in (
		"/app/vetedge-clinical-workspace",
		'doctype !== "Veterinary Consultation"',
		'routeType === "Form"',
		'routeType !== "List"',
		"isNewDocumentRoute",
		'"?new=1"',
	):
		assert contract in route
	assert "/app/vetedge-clinical-workspace" in list_script
	assert "vetedge_clinical_route.js" in hooks


def test_veterinary_home_route_has_a_real_desk_page():
	for path in (
		HOME_PAGE_ROOT / "__init__.py",
		HOME_PAGE_ROOT / "vetedge.js",
		HOME_PAGE_ROOT / "vetedge.json",
	):
		assert path.exists(), path

	hooks = read(HOOKS)
	navigation = read(HOME_NAVIGATION)
	home_script = read(HOME_PAGE_ROOT / "vetedge.js")
	assert 'app_home = "/app/vetedge"' in hooks
	assert 'const HOME_ROUTE = "/app/vetedge"' in navigation
	assert "frappe.pages.vetedge" in home_script
	assert "frappe.set_route('vetedge-executive-dashboard')" in home_script


def test_existing_billing_modal_is_reused_instead_of_reimplemented():
	component = read(COMPONENT)
	assert "window.vetedgeBillingModal.open" in component
	assert 'doctype: "Veterinary Consultation"' in component
	for forbidden in (
		"create_or_update_modal_invoice",
		"record_modal_invoice_payment",
		"submit_modal_invoice",
	):
		assert forbidden not in component
