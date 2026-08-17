from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"


def read(path: str) -> str:
    return (APP / path).read_text()


def test_report_center_prefers_provider_runtime_and_keeps_query_report_fallback():
    center = read("veterinary/page/vetedge_report_center/vetedge_report_center.js")
    adapter = read("public/js/vetedge_report_provider_adapter.js")

    assert "VetEdgeReportProviders" in center
    assert "getProvider?.(this.reportName)" in center
    assert "ensureQueryProvider?.(this.reportName, this.reportName)" in center
    assert 'method: "frappe.desk.query_report.run"' in adapter
    assert "ignore_prepared_report: 1" in adapter
    assert "ignore_user_permissions: 0" in center


def test_report_center_uses_shared_export_builder_and_same_desk_navigation():
    center = read("veterinary/page/vetedge_report_center/vetedge_report_center.js")

    for expected in (
        '"EdgeReportExportDialog"',
        "downloadReportExport",
        '__("Download / Export")',
        "exportOpen",
        "exportBusy",
        "onExport: this.runExport",
        'scope: "all_filtered"',
        'typeof frappe.set_route === "function"',
        "frappe.set_route(...parts)",
        'date_preset: get("date_preset")',
    ):
        assert expected in center


def test_stock_expiry_is_registered_as_query_level_paginated_reference():
    registry = read("public/js/vetedge_report_provider_registry.js")

    assert 'registerPaginatedProvider("Stock Expiry Report"' in registry
    assert "get_stock_expiry_data" in registry
    assert 'pagination_mode: "query-level"' in registry
    assert "limit: pageLength" in registry
    assert "offset: start" in registry
    assert "maxPageLength: 100" in registry


def test_planned_treatment_is_not_misreported_as_query_level_pagination():
    registry = read("public/js/vetedge_report_provider_registry.js")
    service = read("services/treatment_plan_report.py")

    assert 'kind: "paged-response"' in registry
    assert "supports_server_pagination: false" in registry
    assert 'pagination_mode: "materialize-then-slice"' in registry
    assert "optimization_pending: true" in registry
    assert 'execute_structured_report("Planned Treatment", report_filters)' in service
    assert "rows[start : start + page_length]" in service


def test_interactive_provider_contract_stays_read_only_and_export_separate():
    adapter = read("public/js/vetedge_report_provider_adapter.js")
    registry = read("public/js/vetedge_report_provider_registry.js")

    for forbidden in ("ignore_permissions", ".submit()", ".cancel()", "frappe.db.set_value"):
        assert forbidden not in adapter
        assert forbidden not in registry

    assert "export: null" in adapter
    assert "export: null" in registry
    assert "page_length" in adapter
    assert "page_length" in registry
