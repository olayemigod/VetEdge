from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = ROOT / "vetedge" / "services" / "clinical_workspace_context.py"
BUNDLE = ROOT / "vetedge" / "public" / "js" / "vetedge_clinical_workspace.bundle.js"
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
		"loadPatientOwnerContext",
		"Owner:",
		"Tel:",
		"Email:",
		"clinicalContextAwareLinkSearch",
	):
		assert contract in bundle


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
