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
