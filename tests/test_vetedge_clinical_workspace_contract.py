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
PAGE_ROOT = ROOT / "vetedge" / "veterinary" / "page" / "vetedge_clinical_workspace"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_phase_4_uses_a_dedicated_clinical_provider():
    service = read(SERVICE)
    for contract in (
        "def get_consultation_list",
        "def get_consultation_document",
        "def save_consultation_document",
        "def transition_clinical_consultation",
        "def get_vitals_list",
        "def get_vitals_document",
        "def save_vitals_document",
        "def get_clinical_medical_history",
        "def perform_consultation_action",
    ):
        assert contract in service

    assert "CONSULTATION_WRITABLE_FIELDS" in service
    assert "CONSULTATION_CHILD_WRITABLE_FIELDS" in service
    assert "VITALS_WRITABLE_FIELDS" in service
    assert "save_document_workspace" not in service


def test_clinical_payload_cannot_directly_mutate_workflow_billing_or_stock_truth():
    service = read(SERVICE)
    consultation_allowlist = service.split("CONSULTATION_WRITABLE_FIELDS =", 1)[1].split(
        "CONSULTATION_CHILD_WRITABLE_FIELDS =", 1
    )[0]
    for forbidden in (
        '"status"',
        '"payment_status"',
        '"linked_invoice"',
        '"consultation_invoices"',
        '"dispensary_status"',
        '"dispensed_treatments"',
        '"dispensary_stock_entry"',
    ):
        assert forbidden not in consultation_allowlist

    child_allowlist = service.split("CONSULTATION_CHILD_WRITABLE_FIELDS =", 1)[1].split(
        "CONSULTATION_READ_FIELDS =", 1
    )[0]
    for forbidden in (
        '"billing_status"',
        '"payment_status"',
        '"source_document"',
        '"source_detail_name"',
        '"stock_entry_reference"',
    ):
        assert forbidden not in child_allowlist

    for forbidden in (
        'frappe.get_doc("Sales Invoice"',
        'frappe.get_doc("Payment Entry"',
        'frappe.get_doc("Stock Entry"',
        "frappe.db.set_value",
        ".submit()",
        ".cancel()",
    ):
        assert forbidden not in service


def test_existing_controllers_remain_authoritative_for_actions():
    service = read(SERVICE)
    for contract in (
        "transition_consultation_status(name, status)",
        "create_vitals_from_consultation(name, payload)",
        "create_follow_up_from_consultation(",
        "create_lab_order_from_consultation(",
        "create_vaccination_from_consultation(name, values=payload)",
        "create_hospitalisation_from_consultation(consultation_name=name)",
        "confirm_dispensary_issue(name, payload.get(\"dispensed_items\"))",
        "get_consultation_cancellation_preflight",
        "get_patient_medical_history_view",
    ):
        assert contract in service


def test_provider_is_permission_branch_and_conflict_safe():
    service = read(SERVICE)
    for contract in (
        "require_internal_user()",
        "require_vetedge_platform_access",
        "frappe.get_list(",
        'doc.check_permission("read")',
        'doc.check_permission("write")',
        "can_access_consultation",
        "can_access_medical_history",
        "can_access_branch_data",
        "get_assigned_branches",
        "user_has_global_branch_access",
        "frappe.TimestampMismatchError",
        "This clinical record changed after it was opened",
    ):
        assert contract in service

    assert "ignore_permissions=True" not in service


def test_child_rows_preserve_protected_source_and_billing_identity():
    service = read(SERVICE)
    for contract in (
        "def _replace_child_rows_preserving_protected",
        "existing[row_name].items()",
        "payload[\"name\"] = row_name",
        "if key not in SYSTEM_CHILD_FIELDS",
        "doc.append(fieldname, payload)",
    ):
        assert contract in service


def test_frontend_contract_uses_full_edgesuite_runtime():
    for path in (
        SERVICE,
        COMPONENT,
        BUNDLE,
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
        "EdgeFilterBar",
        "EdgeStatCard",
        "EdgeDataTable",
        "EdgeWorkflowBar",
        "EdgeDocumentForm",
        "EdgeLinkField",
        "EdgeModal",
        "EdgeLoadingState",
        "EdgeErrorState",
    ):
        assert contract in component

    for tab in ("Consultations", "Vital Signs", "Medical History"):
        assert tab in component

    assert "frappe.require('edgesuite_ui.bundle.js'" in loader
    assert "const runtime = window.EdgeSuiteUI;" in loader
    assert "frappe.require('edgeui.bundle.js'" not in loader
    assert "const runtime = window.EdgeSuiteUI;" in bundle
    assert "window.EdgeUI" not in bundle
    assert "applyWorkspaceSafety(VetEdgeClinicalWorkspace)" in bundle


def test_native_clinical_routes_redirect_to_workspace():
    consultation_root = ROOT / "vetedge" / "veterinary" / "doctype" / "veterinary_consultation"
    vitals_root = ROOT / "vetedge" / "veterinary" / "doctype" / "veterinary_vital_signs"
    for path, tab in (
        (consultation_root / "veterinary_consultation.js", "consultations"),
        (consultation_root / "veterinary_consultation_list.js", "consultations"),
        (vitals_root / "veterinary_vital_signs.js", "vitals"),
        (vitals_root / "veterinary_vital_signs_list.js", "vitals"),
    ):
        content = read(path)
        assert "/app/vetedge-clinical-workspace" in content
        assert f"tab={tab}" in content


def test_double_review_gate_is_documented_for_phase_4():
    plan = read(ROOT / "docs" / "project_notes" / "vetedge_edgesuite_ui_migration_plan.md")
    assert "Phase 4 — Clinical Documents" in plan
    assert "First clinical review" in plan
    assert "Independent loophole review" in plan
