from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_clinical_record_editor_supports_lab_vaccination_and_vitals():
    service = read(APP / "services/clinical_record_editor.py")
    for doctype in (
        "Veterinary Lab Order",
        "Veterinary Vaccination Record",
        "Veterinary Vital Signs",
    ):
        assert doctype in service
    assert "can_access_branch_data" in service
    assert "ignore_permissions=True" not in service
    assert "doc.save()" in service


def test_clinical_record_editor_is_edgesuite_native_and_billing_aware():
    bundle = read(APP / "public/js/vetedge_clinical_record_editor.bundle.js")
    for contract in (
        "VetEdgeEdgeModalPresenter",
        "Save Changes",
        "Billing & Payment",
        "Open Native Form",
        "EdgeSuite clinical record editor",
    ):
        assert contract in bundle
    assert "frappe.ui.Dialog" not in bundle


def test_resource_center_exposes_edgesuite_clinical_editor_for_lab_and_vaccination():
    bridge = read(APP / "public/js/vetedge_resource_center_clinical_bridge.js")
    assert '"lab-orders": "Veterinary Lab Order"' in bridge
    assert 'vaccinations: "Veterinary Vaccination Record"' in bridge
    assert "View / Edit" in bridge
    assert "VetEdgeClinicalRecordEditor" in bridge


def test_medical_history_readability_and_first_chart_render_are_protected():
    patch = read(APP / "public/js/vetedge_medical_history_qa_patch.js")
    css = read(APP / "public/css/vetedge_medical_history_qa.css")
    for contract in (
        "requestAnimationFrame",
        "Veterinary Lab Order",
        "Veterinary Vaccination Record",
        "Veterinary Vital Signs",
        "VetEdgeClinicalRecordEditor",
    ):
        assert contract in patch
    assert "--edge-color-ink-950" in css
    assert 'data-edge-appearance="dark"' in css
