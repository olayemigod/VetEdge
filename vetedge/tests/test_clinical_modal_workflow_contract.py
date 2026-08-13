from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_clinical_modal_assets_exist_and_are_loaded():
    loader = (ROOT / "vetedge/veterinary/page/vetedge_clinical_workspace/vetedge_clinical_workspace.js").read_text(
        encoding="utf-8"
    )
    expected_assets = (
        "vetedge_edge_modal_presenter.bundle.js",
        "vetedge_billing_edgesuite.bundle.js",
        "vetedge_clinical_workflow_modal.bundle.js",
    )
    for asset in expected_assets:
        assert (ROOT / f"vetedge/public/js/{asset}").exists()
        assert asset in loader


def test_clinical_related_actions_use_shared_presenter():
    bundle = (ROOT / "vetedge/public/js/vetedge_clinical_workspace.bundle.js").read_text(encoding="utf-8")
    assert "RELATED_MODAL_CONFIG" in bundle
    assert "VetEdgeEdgeModalPresenter.open" in bundle
    assert "Veterinary Lab Order" in bundle
    assert "Veterinary Vaccination Record" in bundle
    assert "Veterinary Hospitalisation" in bundle


def test_billing_overlay_is_edgesuite_native():
    billing = (ROOT / "vetedge/public/js/vetedge_billing_edgesuite.bundle.js").read_text(encoding="utf-8")
    assert "VetEdgeEdgeModalPresenter" in billing
    assert "new frappe.ui.Dialog" not in billing
    assert "window.vetedgeBillingModal = { open: openBilling }" in billing


def test_completed_consultation_has_controlled_workflow_entry():
    workflow = (ROOT / "vetedge/public/js/vetedge_clinical_workflow_modal.bundle.js").read_text(encoding="utf-8")
    assert "Reverse / Resolve Consultation" in workflow
    assert "get_consultation_cancellation_preflight" in workflow
