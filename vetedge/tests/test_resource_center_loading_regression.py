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
    action_alignment = read(APP / "public/js/vetedge_resource_center_action_alignment.js")
    bundle = read(APP / "public/js/vetedge_resource_center.bundle.js")

    assert "Medical History" in component
    assert "New Consultation" not in component
    assert "New Lab Order" in component
    assert "New Vaccination" in component
    assert "View / Edit" in component
    assert "clinicalFilters" in component
    assert "clinicalStatusOptions" in component
    assert "row?._display?.[column.fieldname]" in component
    assert "page.summary_label || 'Branch Scope'" in component

    for compatibility in (bridge, hardening, action_alignment):
        assert "Compatibility shim only" in compatibility
        assert "MutationObserver" not in compatibility
    assert "frappe.call = wrapped" not in hardening
    assert "MutationObserver" not in bundle


def test_resource_center_repeat_navigation_syncs_clinical_filters_and_deep_links():
    bundle = read(APP / "public/js/vetedge_resource_center.bundle.js")

    for route_key in (
        "'patient'",
        "'service_branch'",
        "'from_date'",
        "'to_date'",
        "'vaccine'",
        "'lab_test'",
    ):
        assert route_key in bundle
    assert "resourceView.clinicalFilters" in bundle
    assert "resourceView.clinicalFilterLabels" in bundle
    assert "resourceView.openClinicalCreate?.()" in bundle
    assert "resourceView.openClinicalRecord?.({ name: state.name })" in bundle
    assert "CLINICAL_RESOURCES.has(state.resource)" in bundle


def test_resource_center_hides_create_actions_without_create_permission():
    bundle = read(APP / "public/js/vetedge_resource_center.bundle.js")

    assert "if (!this.page?.can_create) return '';" in bundle
    assert "if (this.resource === 'appointments') return 'New Appointment';" in bundle
    assert "if (this.resource === 'lab-orders') return 'New Lab Order';" in bundle
    assert "if (this.resource === 'vaccinations') return 'New Vaccination';" in bundle
