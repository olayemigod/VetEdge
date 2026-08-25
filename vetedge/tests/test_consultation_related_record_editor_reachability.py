import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLINICAL_BUNDLE = ROOT / "vetedge/public/js/vetedge_clinical_workspace.bundle.js"
EDITOR_BUNDLE = ROOT / "vetedge/public/js/vetedge_clinical_record_editor.bundle.js"
WORKFLOW_SERVICE = ROOT / "vetedge/services/clinical_workflow_ui.py"
VACCINATION_META = ROOT / "vetedge/veterinary/doctype/veterinary_vaccination_record/veterinary_vaccination_record.json"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_consultation_lab_and_vaccination_rows_open_existing_edgesuite_editor_lazily():
    clinical = read(CLINICAL_BUNDLE)

    for contract in (
        "async function openRelatedClinicalRecord",
        "vetedge_clinical_record_editor.bundle.js",
        "window.VetEdgeClinicalRecordEditor?.open",
        "label: tr('Open')",
        "onSaved: async () =>",
        "await view.loadDetail?.(consultation)",
        "await refresh?.()",
    ):
        assert contract in clinical

    assert "frappe.set_route(\"Form\", doctype, row.name)" not in clinical


def test_related_record_open_action_coexists_with_permission_aware_safe_delete():
    clinical = read(CLINICAL_BUNDLE)
    start = clinical.index("function relatedRowActions")
    end = clinical.index("\nfunction showRelatedRecords", start)
    block = clinical[start:end]

    assert "Veterinary Lab Order" in block
    assert "Veterinary Vaccination Record" in block
    assert "label: tr('Open')" in block
    assert "if (row.can_delete)" in block
    assert "delete_consultation_related_record" in block
    assert block.index("label: tr('Open')") < block.index("if (row.can_delete)")


def test_consultation_vaccination_route_uses_select_and_matches_doctype_options():
    clinical = read(CLINICAL_BUNDLE)
    metadata = json.loads(read(VACCINATION_META))
    route_field = next(field for field in metadata["fields"] if field.get("fieldname") == "route")
    expected = [value.strip() for value in str(route_field.get("options") or "").splitlines() if value.strip()]

    assert route_field.get("fieldtype") == "Select"
    assert expected
    assert "const VACCINATION_ROUTE_OPTIONS = Object.freeze(" in clinical
    for value in expected:
        assert repr(value) in clinical
    assert "fieldname: 'route', label: tr('Route'), type: 'select'" in clinical
    assert "options: VACCINATION_ROUTE_OPTIONS.map" in clinical
    assert "fieldname: 'route', label: tr('Route'), type: 'text'" not in clinical


def test_existing_editor_and_server_workflow_remain_authoritative_for_lab_progress_and_results():
    editor = read(EDITOR_BUNDLE)
    workflow = read(WORKFLOW_SERVICE)

    for contract in (
        'workflow: "vetedge.services.clinical_workflow_ui.get_clinical_workflow_actions"',
        "Enter Result",
        "View / Edit Result",
        "Upload Result",
        "Change Price",
        "Billing & Payment",
    ):
        assert contract in editor

    for contract in (
        '"Ordered"',
        '"Sample Collected"',
        '"Sent to Lab"',
        '"In Progress"',
        '"Result Pending"',
        '"Result Entered"',
        '"Awaiting Review"',
        '"Reviewed"',
        '"Completed"',
        "_lab_payment_gate",
        "_lab_completion_gate",
        "can_enter_lab_results",
        "can_review_lab_results",
    ):
        assert contract in workflow
