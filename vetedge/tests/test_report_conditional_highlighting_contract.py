from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPERATIONS_UI = ROOT / "public/js/vetedge_hospitalisation_operations/VetEdgeHospitalisationOperations.vue"


def test_hospitalisation_conditional_highlighting_uses_shared_row_presentation_contract():
    source = OPERATIONS_UI.read_text(encoding="utf-8")

    for expected in (
        ':rowPresentation="advancedExceptionsEntitled ? rowPresentation : null"',
        "rowPresentation(row)",
        "if (!this.advancedExceptionsEntitled || !row) return {}",
        "Number(row.missing_price_count || 0) > 0",
        "Number(row.pending_stock_count || 0) > 0",
        "Number(row.pending_billable_activity_count || 0) > 0",
        "tone: 'danger'",
        "tone: 'warning'",
        "tone: 'info'",
    ):
        assert expected in source


def test_highlighting_reuses_existing_operational_truth_and_adds_no_api_request():
    source = OPERATIONS_UI.read_text(encoding="utf-8")
    method = source.split("rowPresentation(row)", 1)[1].split("syncShellContext()", 1)[0]

    assert "frappe.call" not in method
    assert "callFrappe" not in method
    assert "fetchExceptions" not in method
    assert "fetchData" not in method
    assert "missing_price_count" in method
    assert "pending_stock_count" in method
    assert "pending_billable_activity_count" in method


def test_highlight_precedence_matches_operational_severity():
    source = OPERATIONS_UI.read_text(encoding="utf-8")
    method = source.split("rowPresentation(row)", 1)[1].split("syncShellContext()", 1)[0]

    assert method.index("missing_price_count") < method.index("pending_stock_count")
    assert method.index("pending_stock_count") < method.index("pending_billable_activity_count")
    assert method.index("tone: 'danger'") < method.index("tone: 'warning'") < method.index("tone: 'info'")


def test_standard_plan_does_not_receive_advanced_highlighting():
    source = OPERATIONS_UI.read_text(encoding="utf-8")

    assert ':rowPresentation="advancedExceptionsEntitled ? rowPresentation : null"' in source
    assert "advancedExceptionsEntitled()" in source
    assert "exceptionCapabilities?.advanced_features_entitled" in source
