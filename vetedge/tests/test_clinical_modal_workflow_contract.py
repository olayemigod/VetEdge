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


def test_billing_invoice_actions_are_inline_and_payment_is_row_scoped():
    billing = (ROOT / "vetedge/public/js/vetedge_billing_edgesuite.bundle.js").read_text(encoding="utf-8")
    presenter = (ROOT / "vetedge/public/js/vetedge_edge_modal_presenter.bundle.js").read_text(encoding="utf-8")

    assert "rowActions: invoiceActionGroups(state, linkedRows, controller)" in billing
    assert "rowActions: invoiceActionGroups(state, patientRows, controller)" in billing
    assert "renderInlineActionTable" in presenter
    assert "vetedge-edge-inline-table__actions" in presenter
    assert 'h("th", { class: "vetedge-edge-inline-table__action-heading" }, __("Action"))' in presenter

    assert "...(state.patient_outstanding_context || [])" in billing
    assert "payableRows(state, invoice)" in billing
    assert "const selectedInvoice = invoice.name || invoice.invoice" in billing
    assert "amount: selectedAmount" in billing
    assert "modalView.update({ values: { ...values, invoice: value, amount: selected.outstanding_amount || 0 } })" in billing


def test_completed_consultation_has_controlled_workflow_entry():
    workflow = (ROOT / "vetedge/public/js/vetedge_clinical_workflow_modal.bundle.js").read_text(encoding="utf-8")
    assert "Reverse / Resolve Consultation" in workflow
    assert "get_consultation_cancellation_preflight" in workflow
