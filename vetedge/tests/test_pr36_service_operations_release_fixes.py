from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (APP_ROOT / relative_path).read_text(encoding="utf-8")


def test_hospital_services_rows_and_details_use_display_labels():
    source = _read("services/service_operations.py")

    assert "from vetedge.services.display_labels import enrich_link_display_values, get_display_label" in source
    assert "enrich_link_display_values(rows, columns)" in source
    assert 'payload["raw_value"] = value' in source
    assert 'payload["value"] = get_display_label(field.options, value)' in source
    assert '"title": _document_title(doc)' in source


def test_boarding_checkout_uses_billing_core_authority_when_enabled():
    source = _read("services/boarding_checkout_alignment.py")
    operations = _read("services/service_operations.py")

    assert "get_source_payment_gate_status" in source
    assert "sync_source_to_billing_session" in source
    assert "validate_legacy_boarding_checkout_billing(doc)" in source
    assert '"check-out": check_out_boarding_booking_doc_aligned' in operations


def test_billing_presenter_is_elevated_above_workflow_modals():
    source = _read("public/js/vetedge_billing_modal_layering.js")

    assert "function elevateEdgeBillingPresenter()" in source
    assert ".vetedge-edge-modal-presenter-host" in source
    assert "elevateEdgeBillingPresenter();" in source
