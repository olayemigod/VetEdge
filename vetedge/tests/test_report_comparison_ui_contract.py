from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "veterinary/page/vetedge_report_center/vetedge_report_center.js"


def test_report_center_uses_shared_comparison_panel_and_advanced_feature_gate():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        'REPORT_COMPARISON_API = "vetedge.services.report_comparison.get_report_comparison"',
        "EdgeReportComparisonPanel = runtime.components.EdgeReportComparisonPanel || null",
        'this.reportName === "Consultation Register"',
        "this.capabilities.advanced_features_entitled",
        '__("Compare Previous Period")',
        '__("Compare · Advanced")',
        "renderInsights()",
    ):
        assert expected in source


def test_comparison_request_is_aggregate_only_and_does_not_reload_detail_provider():
    source = SOURCE.read_text(encoding="utf-8")
    method = source.split("async loadComparison()", 1)[1].split("renderChart()", 1)[0]

    assert "frappe.call(REPORT_COMPARISON_API" in method
    assert "filters: JSON.stringify(this.reportFilters())" in method
    assert "provider.load" not in method
    assert "this.refresh(" not in method
    assert "pageStart" not in method
    assert "pageLength" not in method


def test_filter_refresh_invalidates_old_comparison_but_pagination_does_not_refetch_it():
    source = SOURCE.read_text(encoding="utf-8")
    set_filter = source.split("setFilter(field, value)", 1)[1].split("reportFilters()", 1)[0]
    refresh = source.split("async refresh(resetPage = false)", 1)[1].split("goToPage(pageNumber)", 1)[0]
    pagination = source.split("goToPage(pageNumber)", 1)[1].split("setPageSize(size)", 1)[0]

    assert "this.comparison = null" in set_filter
    assert "if (resetPage)" in refresh
    assert "this.comparison = null" in refresh
    assert "loadComparison" not in pagination


def test_comparison_component_is_optional_for_backward_runtime_compatibility():
    source = SOURCE.read_text(encoding="utf-8")
    required_block = source.split("const required =", 1)[1].split("const missing", 1)[0]

    assert "EdgeReportComparisonPanel" not in required_block
    assert "Boolean(EdgeReportComparisonPanel" in source
