from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "veterinary/page/vetedge_report_center/vetedge_report_center.js"


def test_report_center_uses_shared_grouping_panel_and_advanced_feature_gate():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        'REPORT_GROUPING_API = "vetedge.services.report_grouping.get_report_grouping"',
        "EdgeReportGroupingPanel = runtime.components.EdgeReportGroupingPanel || null",
        'this.reportName === "Consultation Register"',
        "this.capabilities.advanced_features_entitled",
        '__("Group by Branch")',
        '__("Group by Practitioner")',
        '__("Group by Consultation Type")',
        '__("Group by Status")',
        "renderInsights()",
    ):
        assert expected in source


def test_grouping_request_is_aggregate_only_and_does_not_reload_detail_provider():
    source = SOURCE.read_text(encoding="utf-8")
    method = source.split("async loadGrouping(dimension)", 1)[1].split("renderChart()", 1)[0]

    assert "frappe.call(REPORT_GROUPING_API" in method
    assert "filters: JSON.stringify(this.reportFilters())" in method
    assert "provider.load" not in method
    assert "this.refresh(" not in method
    assert "pageStart" not in method
    assert "pageLength" not in method


def test_filter_or_saved_view_change_invalidates_grouping_but_pagination_does_not_refetch_it():
    source = SOURCE.read_text(encoding="utf-8")
    set_filter = source.split("setFilter(field, value)", 1)[1].split("reportFilters()", 1)[0]
    saved_view = source.split("async applySavedView(viewId)", 1)[1].split("promptSaveView", 1)[0]
    pagination = source.split("goToPage(pageNumber)", 1)[1].split("setPageSize(size)", 1)[0]

    for block in (set_filter, saved_view):
        assert "this.invalidateInsightRequests()" in block
        assert "this.grouping = null" in block
        assert 'this.groupingDimension = ""' in block
    assert "loadGrouping" not in pagination


def test_grouping_ignores_late_response_after_filter_or_dimension_signature_changes():
    source = SOURCE.read_text(encoding="utf-8")
    method = source.split("async loadGrouping(dimension)", 1)[1].split("renderChart()", 1)[0]

    assert "const generation = ++this.groupingRequestGeneration" in method
    assert "const signature = this.insightRequestSignature({ dimension: this.groupingDimension })" in method
    assert "generation !== this.groupingRequestGeneration" in method
    assert "signature !== this.insightRequestSignature({ dimension: this.groupingDimension })" in method
    assert "this.grouping = response.message || null" in method
    assert method.index("generation !== this.groupingRequestGeneration") < method.index("this.grouping = response.message || null")


def test_grouping_component_is_optional_for_backward_runtime_compatibility():
    source = SOURCE.read_text(encoding="utf-8")
    required_block = source.split("const required =", 1)[1].split("const missing", 1)[0]

    assert "EdgeReportGroupingPanel" not in required_block
    assert "Boolean(EdgeReportGroupingPanel" in source
