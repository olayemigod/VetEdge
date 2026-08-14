from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_resource_center_mounts_before_optional_clinical_enhancements():
    loader = read(APP / "veterinary/page/vetedge_resource_center/vetedge_resource_center.js")
    resource_bundle = "frappe.require('vetedge_resource_center.bundle.js'"
    clinical_presenter = "frappe.require('vetedge_edge_modal_presenter.bundle.js'"
    clinical_editor = "frappe.require('vetedge_clinical_record_editor.bundle.js'"

    assert resource_bundle in loader
    assert clinical_presenter in loader
    assert clinical_editor in loader
    assert loader.index(resource_bundle) < loader.index(clinical_presenter)
    assert loader.index("wrapper.vue_app = window.mountVetEdgeResourceCenter") < loader.index(clinical_presenter)
    assert "progressive enhancements" in loader


def test_resource_center_clinical_bridge_is_idempotent_and_ignores_its_own_mutations():
    bridge = read(APP / "public/js/vetedge_resource_center_clinical_bridge.js")

    assert 'String(existing.textContent || "").trim() !== label' in bridge
    assert "function isBridgeOwnedNode" in bridge
    assert "data-edge-clinical-create" in bridge
    assert "data-edge-clinical-editor" in bridge
    assert "data-edge-registration-billing" in bridge
    assert "td[data-patient-id]" in bridge
    assert "changed.some((node) => !isBridgeOwnedNode(node))" in bridge
    assert "records.some(mutationNeedsDecoration)" in bridge
    assert "scheduleDecoration(root)" in bridge
    assert 'String(cell.textContent || "").trim() !== String(label)' in bridge
    assert "get_patient_labels" in bridge
