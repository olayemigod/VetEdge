from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = ROOT / "vetedge" / "services" / "clinical_workspace_context.py"
BUNDLE = ROOT / "vetedge" / "public" / "js" / "vetedge_clinical_workspace.bundle.js"
PAGE_LOADER = (
	ROOT
	/ "vetedge"
	/ "veterinary"
	/ "page"
	/ "vetedge_clinical_workspace"
	/ "vetedge_clinical_workspace.js"
)
TREATMENT_ITEMS = ROOT / "vetedge" / "services" / "treatment_items.py"
HOOKS = ROOT / "vetedge" / "hooks.py"
HOME = ROOT / "vetedge" / "veterinary" / "page" / "vetedge" / "vetedge.js"
HOME_JSON = ROOT / "vetedge" / "veterinary" / "page" / "vetedge" / "vetedge.json"
CLINICAL_JSON = (
	ROOT
	/ "vetedge"
	/ "veterinary"
	/ "page"
	/ "vetedge_clinical_workspace"
	/ "vetedge_clinical_workspace.json"
)
PAGE_ROLE_PATCH = ROOT / "vetedge" / "patches" / "ensure_vetedge_operational_page_roles.py"
PATCHES = ROOT / "vetedge" / "patches.txt"


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_doctor_ownership_is_enforced_server_side_and_in_the_workspace():
	context = read(CONTEXT)
	hooks = read(HOOKS)
	bundle = read(BUNDLE)

	for contract in (
		"def is_restricted_doctor",
		"def assert_consultation_write_ownership",
		"def enforce_consultation_practitioner_ownership",
		"def enforce_vitals_consultation_ownership",
		"A doctor cannot save a consultation for another doctor.",
	):
		assert contract in context

	assert "clinical_workspace_context.enforce_consultation_practitioner_ownership" in hooks
	assert "clinical_workspace_context.enforce_vitals_consultation_ownership" in hooks
	for contract in (
		"restrictedDoctor",
		"startNewConsultationWithDoctorOwnership",
		"assignedDoctor !== currentUser()",
		"this.detail.can_write = false",
		"this.detail.capabilities.create_vitals = false",
	):
		assert contract in bundle


def test_patient_owner_and_consultation_type_context_are_visible_and_provider_driven():
	context = read(CONTEXT)
	bundle = read(BUNDLE)

	for contract in (
		"def get_clinical_context_options",
		"def get_patient_owner_context",
		'kind == "practitioner"',
		'kind != "consultation_type"',
		'"mobile_no"',
		'"email_id"',
		'"emergency_contact"',
		'"default_branch"',
	):
		assert contract in context

	for contract in (
		"CLINICAL_CONTEXT_API",
		"VetEdgeClinicalWorkspace.methods.loadPatientOwnerContext = async function loadPatientOwnerContext",
		"createClinicalLinkField",
		"reactive(new Map())",
		"patientLabelById",
		"selectedLabel: props.selectedLabel || patientLabel",
		"vetedge-owner-summary",
		"Pet Owner",
		"View Owner Details",
		"showOwnerDetails",
		"clinicalContextAwareLinkSearch",
	):
		assert contract in bundle
	assert "const patientLabelById = new Map()" not in bundle

	owner_summary = bundle.split("VetEdgeClinicalWorkspace.methods.syncOwnerDetailsButton", 1)[1].split(
		"const originalTreatmentRowLocked", 1
	)[0]
	assert "owner.email_id" not in owner_summary
	assert "patient.emergency_contact" not in owner_summary

	loader_definition = bundle.index(
		"VetEdgeClinicalWorkspace.methods.loadPatientOwnerContext = async function loadPatientOwnerContext"
	)
	apply_detail_call = bundle.index("this.loadPatientOwnerContext(this.form.patient, false)")
	patient_change_call = bundle.index("this.loadPatientOwnerContext(value || '')")
	assert loader_definition < apply_detail_call
	assert loader_definition < patient_change_call


def test_clinical_workspace_has_persistent_and_keyboard_save_actions():
	loader = read(PAGE_LOADER)
	for contract in (
		"vetedge-clinical-save-dock",
		"event.ctrlKey || event.metaKey",
		"String(event.key || '').toLowerCase() !== 's'",
		"event.preventDefault()",
		"workspace.saveConsultation()",
		"workspace?.vitalsDialog?.open",
		"workspace?.historyDialog?.open",
		"document.addEventListener('keydown', saveShortcutHandler)",
		"document.removeEventListener('keydown', saveShortcutHandler)",
	):
		assert contract in loader


def test_treatment_item_lookup_orders_recent_profiles_first():
	treatment_items = read(TREATMENT_ITEMS)
	assert "ORDER BY treatment.modified DESC, item.item_name ASC, item.name ASC" in treatment_items


def test_veterinary_home_is_role_aware_for_doctors_and_operational_roles():
	home = read(HOME)
	for contract in (
		"resolveVetEdgeHomeRoute",
		"VetEdge Doctor",
		"vetedge-clinical-workspace",
		"VetEdge Front Desk",
		"vetedge-front-desk-action-center",
		"VetEdge Administrator",
		"vetedge-executive-dashboard",
	):
		assert contract in home


def test_operational_page_role_aliases_are_source_controlled_and_migrated():
	home_json = read(HOME_JSON)
	clinical_json = read(CLINICAL_JSON)
	patch = read(PAGE_ROLE_PATCH)
	patches = read(PATCHES)

	for role in ("VetEdge Doctor", "Veterinary Nurse", "VetEdge Nurse"):
		assert role in home_json
		assert role in clinical_json
		assert role in patch
	assert '"vetedge"' in patch
	assert '"vetedge-clinical-workspace"' in patch
	assert "page.append(\"roles\", {\"role\": role})" in patch
	assert "vetedge.patches.ensure_vetedge_operational_page_roles" in patches
