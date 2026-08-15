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
    mount_call = "wrapper.vue_app = window.mountVetEdgeResourceCenter(root[0])"
    enhancement_call = "loadClinicalEnhancements(root[0])"

    assert resource_bundle in loader
    assert clinical_presenter in loader
    assert clinical_editor in loader
    assert mount_call in loader
    assert enhancement_call in loader
    assert loader.index(mount_call) < loader.index(enhancement_call)
    assert "must not install a second billing renderer" in loader


def test_resource_center_source_replaces_legacy_dom_bridges():
    component = read(APP / "public/js/vetedge_resource_center/VetEdgeResourceCenter.vue")
    bridge = read(APP / "public/js/vetedge_resource_center_clinical_bridge.js")
    hardening = read(APP / "public/js/vetedge_resource_center_hardening.js")

    assert "New Consultation" in component
    assert "New Lab Order" in component
    assert "New Vaccination" in component
    assert "View / Edit" in component
    assert "clinicalFilters" in component
    assert "clinicalStatusOptions" in component
    assert "row?._display?.[column.fieldname]" in component
    assert "page.summary_label || 'Branch Scope'" in component

    assert "Compatibility shim only" in bridge
    assert "Compatibility shim only" in hardening
    assert "MutationObserver" not in bridge
    assert "MutationObserver" not in hardening
    assert "frappe.call = wrapped" not in hardening
