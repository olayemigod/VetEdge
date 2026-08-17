from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"


def test_vetedge_report_provider_adapter_prefers_shared_edgesuite_runtime():
    source = (APP / "public/js/vetedge_report_provider_adapter.js").read_text()

    for expected in (
        'global.EdgeSuiteReports || global.EdgeSuiteUI?.reports || global.EdgeUI?.reports',
        'shared?.createQueryReportProvider',
        'shared?.registerProvider?.(PRODUCT, reportKey, provider)',
        'shared.createPaginatedReportProvider({ key: reportKey, ...options })',
        'shared.registerProvider(PRODUCT, reportKey, provider)',
        'normalizePayload(payload, request)',
        'supports_server_pagination: false',
    ):
        assert expected in source


def test_vetedge_report_provider_adapter_keeps_safe_backward_compatibility():
    source = (APP / "public/js/vetedge_report_provider_adapter.js").read_text()

    for expected in (
        'method: "frappe.desk.query_report.run"',
        'ignore_prepared_report: 1',
        'are_default_filters: false',
        'fallbackQueryProvider',
        'export: null',
    ):
        assert expected in source

    for forbidden in (
        'ignore_permissions',
        'setInterval(',
        'frappe.db.set_value',
        '.submit()',
        '.cancel()',
    ):
        assert forbidden not in source


def test_stock_expiry_monitor_uses_shared_report_shell_and_server_pagination():
    component = (APP / "public/js/vetedge_stock_expiry_monitor/VetedgeStockExpiryMonitor.vue").read_text()
    page = (APP / "veterinary/page/stock_expiry_monitor/stock_expiry_monitor.js").read_text()

    for expected in (
        '<EdgeReportShell',
        ':pagination="pagination"',
        '@page-change="goToPage"',
        '@page-size-change="setPageSize"',
        ':exportEnabled="capabilities.can_export"',
        ':printEnabled="capabilities.can_print"',
        'search_stock_expiry_filter_options',
        'page_length: 20',
        'download_stock_expiry_export',
        'get_stock_expiry_print_html',
    ):
        assert expected in component

    assert "'EdgeReportShell'" in page
    assert "limit_page_length: 500" not in component
    assert "<table" not in component
    assert "pagination-footer" not in component


def test_stock_expiry_shell_actions_are_read_only_and_reauthorize():
    source = (APP / "services/stock_expiry_reporting_actions.py").read_text()

    for expected in (
        '@frappe.read_only()',
        'check_expiry_permissions()',
        'require_reporting_action(SCOPE_NAME, scope_type="report", action="export")',
        'require_reporting_action(SCOPE_NAME, scope_type="report", action="print")',
        'get_stock_expiry_rows(filters_dict)',
        '_validate_reference_filter(value, "warehouse")',
        '_validate_reference_filter(value, "item_group")',
        'get_summary(source_rows)',
        'get_status_chart(summary)',
        'MAX_CURRENT_PAGE_LENGTH',
    ):
        assert expected in source

    for forbidden in (
        'ignore_permissions',
        'frappe.db.set_value',
        '.submit()',
        '.cancel()',
        'frappe.delete_doc',
    ):
        assert forbidden not in source
