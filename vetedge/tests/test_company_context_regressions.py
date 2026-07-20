from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPAT = ROOT / "vetedge" / "services" / "company_context_compat.py"
MEDICAL_HISTORY = ROOT / "vetedge" / "services" / "medical_history_context.py"
APPOINTMENT_CONTEXT = ROOT / "vetedge" / "services" / "appointment_context_api.py"
PATIENT_SERVICE = ROOT / "vetedge" / "services" / "patient.py"
HOOKS = ROOT / "vetedge" / "hooks.py"
DASHBOARD_INSTALL = ROOT / "vetedge" / "install" / "dashboard.py"
PATCHES = ROOT / "vetedge" / "patches.txt"


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_company_repair_is_idempotent_and_does_not_touch_accounting_documents():
	content = read(COMPAT)
	for contract in (
		"get_patient_company_context",
		"repair_patient_company",
		"repair_resolvable_company_context",
		"sync_branch_company_context",
		"update_modified=False",
		"IFNULL(a.docstatus, 0) = 0",
	):
		assert contract in content
	for forbidden in (
		'frappe.db.set_value("Sales Invoice"',
		'frappe.db.set_value("Payment Entry"',
		'frappe.db.set_value("Stock Entry"',
		"UPDATE `tabSales Invoice`",
		"UPDATE `tabPayment Entry`",
		"UPDATE `tabStock Entry`",
	):
		assert forbidden not in content


def test_legacy_patients_are_resolved_during_search_and_selection():
	content = read(APPOINTMENT_CONTEXT)
	for contract in (
		"_search_patients",
		"patient_is_available_for_company",
		"legacy_company_context",
		"def get_patient_selection_context(patient: str)",
		"repair_patient_company(patient, company)",
		"repair_patient_company(payload[\"patient\"], branch[\"company\"])",
	):
		assert contract in content
	assert 'filters["company"] = company' not in content
	assert 'filters["default_branch"]' not in content
	assert "ignore_permissions" not in content


def test_native_patient_creation_inherits_working_branch_and_company():
	content = read(PATIENT_SERVICE)
	for contract in (
		"get_working_branch_name",
		"get_branch_company(doc.default_branch)",
		"get_working_company",
		"validate_patient_company_context",
		"Default Branch {0} belongs to Company {1}",
	):
		assert contract in content


def test_medical_history_keeps_patient_linked_historical_records_visible():
	content = read(MEDICAL_HISTORY)
	for contract in (
		"validate_patient_history_access(patient)",
		"base.get_consultation_history",
		"base.get_vitals_history",
		"base.get_diagnosis_history",
		"base.get_symptom_history",
		"base.get_treatment_history",
		"base.get_lab_history",
		"base.get_vaccination_history",
		"they are not required to carry a newly introduced Company field",
	):
		assert contract in content
	assert 'filters={"company"' not in content


def test_hooks_route_home_and_compatibility_services():
	content = read(HOOKS)
	for contract in (
		'app_home = "/app/vetedge-home"',
		"override_whitelisted_methods",
		"medical_history_context.get_patient_medical_history_view",
		'"Branch": {',
		"company_context_compat.sync_branch_company_context",
	):
		assert contract in content


def test_veterinary_home_is_injected_into_canonical_sidebar():
	content = read(DASHBOARD_INSTALL)
	for contract in (
		'VETEDGE_DESK_ROUTE = "/app/vetedge-home"',
		"VETERINARY_HOME_ITEM",
		'"label": "Veterinary Home"',
		'"link_to": "vetedge-home"',
		"_with_veterinary_home",
		"kept_items = _with_veterinary_home",
	):
		assert contract in content


def test_reconciliation_patch_runs_after_branch_fields_exist():
	patches = read(PATCHES)
	branch_fields = patches.index("vetedge.patches.ensure_veterinary_branch_context_fields")
	branch_backfill = patches.index("vetedge.patches.backfill_veterinary_company_from_branch")
	reconciliation = patches.index("vetedge.patches.reconcile_veterinary_company_context_v2")
	assert branch_fields < branch_backfill < reconciliation
