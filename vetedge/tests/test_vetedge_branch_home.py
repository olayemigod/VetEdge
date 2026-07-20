from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRANCH_CONTEXT = ROOT / "vetedge" / "services" / "branch_context.py"
COMPANY_CONTEXT = ROOT / "vetedge" / "services" / "company_context.py"
COMPANY_COMPAT = ROOT / "vetedge" / "services" / "company_context_compat.py"
APPOINTMENT_CONTEXT = ROOT / "vetedge" / "services" / "appointment_context_api.py"
HOME_API = ROOT / "vetedge" / "services" / "home.py"
HOME_VUE = ROOT / "vetedge" / "public" / "js" / "vetedge_home" / "VetEdgeHome.vue"
HOME_BUNDLE = ROOT / "vetedge" / "public" / "js" / "vetedge_home.bundle.js"
HOME_LOADER = ROOT / "vetedge" / "veterinary" / "page" / "vetedge_home" / "vetedge_home.js"
RESOURCE_LOADER = ROOT / "vetedge" / "veterinary" / "page" / "vetedge_resource_center" / "vetedge_resource_center.js"
RESOURCE_CONTEXT_BUNDLE = ROOT / "vetedge" / "public" / "js" / "vetedge_resource_center_context.bundle.js"
BRANCH_PATCH = ROOT / "vetedge" / "patches" / "ensure_veterinary_branch_context_fields.py"
BACKFILL_PATCH = ROOT / "vetedge" / "patches" / "backfill_veterinary_company_from_branch.py"
RECONCILE_PATCH = ROOT / "vetedge" / "patches" / "reconcile_veterinary_company_context_v2.py"
PATCHES = ROOT / "vetedge" / "patches.txt"
HOOKS = ROOT / "vetedge" / "hooks.py"
DASHBOARD_INSTALL = ROOT / "vetedge" / "install" / "dashboard.py"


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_branch_context_is_permission_aware_and_persists_working_defaults():
	content = read(BRANCH_CONTEXT)
	for contract in (
		"get_allowed_veterinary_branches",
		"get_active_veterinary_branch_context",
		"validate_working_branch",
		"switch_veterinary_branch",
		"get_assigned_branches",
		"user_has_global_branch_access",
		"frappe.defaults.set_user_default(USER_BRANCH_KEY",
		"frappe.defaults.set_user_default(USER_COMPANY_KEY",
		'frappe.defaults.set_user_default("company"',
		'frappe.defaults.set_user_default("branch"',
		'"cost_center"',
		'"default_warehouse"',
		'"price_list"',
	):
		assert contract in content

	assert "ignore_permissions" not in content


def test_active_company_is_derived_from_the_working_branch_before_platform_fallback():
	content = read(COMPANY_CONTEXT)
	working = content.index("company = _working_branch_company(user)")
	platform = content.index("company = _clean(get_current_vetedge_company(user))")
	assert working < platform


def test_patient_search_resolves_legacy_company_without_branch_hiding():
	content = read(APPOINTMENT_CONTEXT)
	for contract in (
		"get_active_veterinary_branch_context",
		"_search_patients",
		"patient_is_available_for_company",
		"get_patient_company_context",
		"customer_is_allowed_for_company",
		"legacy_company_context",
		"Fetch permission-aware candidates",
		"return _search_patients",
	):
		assert contract in content
	assert 'filters["company"] = company' not in content
	assert 'filters["default_branch"]' not in content
	assert "ignore_permissions" not in content


def test_patient_selection_and_appointment_creation_repair_only_unambiguous_context():
	api = read(APPOINTMENT_CONTEXT)
	bundle = read(RESOURCE_CONTEXT_BUNDLE)
	for contract in (
		"def get_patient_selection_context(patient: str)",
		"patient_is_available_for_company(patient, company)",
		"repair_patient_company(patient, company)",
		"return base.get_patient_selection_context(patient, resolved_company)",
		"repair_patient_company(payload[\"patient\"], branch[\"company\"])",
	):
		assert contract in api
	assert "appointment_context_api.get_patient_selection_context" in bundle
	assert "appointment_edgeui.get_patient_selection_context" not in bundle


def test_appointment_dialog_loads_working_branch_bootstrap_and_context_api():
	bundle = read(RESOURCE_CONTEXT_BUNDLE)
	loader = read(RESOURCE_LOADER)
	for contract in (
		"appointment_context_api.get_appointment_form_bootstrap",
		"appointment_context_api.search_appointment_link",
		"appointment_context_api.create_edgeui_appointment",
		"Working context:",
		"Change the working branch from Veterinary Home",
		"searchPatient(query){return this.searchLink('patient',query,{company:this.bootstrap.active_company})",
	):
		assert contract in bundle
	assert "vetedge_resource_center_context.bundle.js" in loader
	assert "mountVetEdgeResourceCenterContext" in loader
	assert "EdgeSuite UI 0.4.1 or newer" in loader


def test_veterinary_home_uses_shared_branch_component_and_role_filtered_navigation():
	api = read(HOME_API)
	vue = read(HOME_VUE)
	bundle = read(HOME_BUNDLE)
	loader = read(HOME_LOADER)
	for contract in (
		"MENU_DEFINITIONS",
		"MODULE_DEFINITIONS",
		"VetEdge Front Desk",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"VetEdge Groomer",
		"Dispensary User",
		"Lab Technician",
		"Accounts/Cashier",
		"Branch Manager",
		'frappe.has_permission(doctype, "read")',
		"get_active_veterinary_branch_context",
		'fields=[{"COUNT": "*", "as": "total"}]',
	):
		assert contract in api
	for contract in (
		"EdgeAppShell",
		"EdgeBranchContextSwitcher",
		"switch_veterinary_branch",
		"edgesuite:branch-context-changed",
		"active_defaults",
		"Cost Center",
		"Warehouse",
		"Price List",
	):
		assert contract in vue
	assert "mountVetEdgeHome" in bundle
	assert "EdgeBranchContextSwitcher" in bundle
	assert "vetedge_home.bundle.js" in loader
	assert "EdgeSuite UI 0.4.1 or newer" in loader


def test_veterinary_home_is_canonical_app_and_product_menu_entry():
	hooks = read(HOOKS)
	install = read(DASHBOARD_INSTALL)
	for contract in (
		'app_home = "/app/vetedge-home"',
		'"route": app_home',
	):
		assert contract in hooks
	for contract in (
		'VETEDGE_DESK_ROUTE = "/app/vetedge-home"',
		"VETERINARY_HOME_ITEM",
		'"label": "Veterinary Home"',
		'"link_to": "vetedge-home"',
		"_with_veterinary_home",
		"kept_items = _with_veterinary_home",
	):
		assert contract in install


def test_branch_fields_and_patient_company_reconciliation_are_migration_safe():
	branch_patch = read(BRANCH_PATCH)
	backfill = read(BACKFILL_PATCH)
	reconcile = read(RECONCILE_PATCH)
	compat = read(COMPANY_COMPAT)
	patches = read(PATCHES)
	for fieldname in (
		"vetedge_company",
		"vetedge_cost_center",
		"vetedge_default_warehouse",
	):
		assert fieldname in branch_patch
	assert "len(companies) == 1" in branch_patch
	assert "INNER JOIN `tabBranch` b ON b.name = p.default_branch" in backfill
	assert "IFNULL(b.vetedge_company, '') != ''" in backfill
	assert "repair_resolvable_company_context()" in reconcile
	assert "sync_branch_company_context" in compat
	assert 'IFNULL(company, "")' not in compat
	assert "update_modified=False" in compat
	assert "IFNULL(a.docstatus, 0) = 0" in compat
	assert "vetedge.patches.ensure_veterinary_branch_context_fields" in patches
	assert "vetedge.patches.backfill_veterinary_company_from_branch" in patches
	assert "vetedge.patches.reconcile_veterinary_company_context_v2" in patches
