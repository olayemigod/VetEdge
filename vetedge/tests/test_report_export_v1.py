from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"


def read(path: str) -> str:
    return (APP / path).read_text()


def test_server_export_uses_frappe_permission_aware_report_runner_and_supported_generators():
    service = read("services/report_export.py")

    for expected in (
        "from frappe.desk.query_report import run as run_query_report",
        "from frappe.utils.xlsxutils import make_xlsx",
        "from frappe.utils.pdf import get_chrome_pdf, get_pdf",
        "ignore_prepared_report=True",
        "are_default_filters=False",
        '"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"',
        '"text/csv; charset=utf-8"',
        '"application/pdf"',
        "@frappe.read_only()",
    ):
        assert expected in service

    for forbidden in ("ignore_permissions", "frappe.db.set_value", ".submit()", ".cancel()"):
        assert forbidden not in service


def test_raw_export_contract_and_server_side_all_filtered_execution():
    service = read("services/report_export.py")

    assert 'normalized["raw_table_only"] = not any' in service
    assert 'scope not in {"current_page", "all_filtered"}' in service
    assert 'if options["scope"] != "current_page"' in service
    assert "payload = _run_report(report_name, filters_dict)" in service
    assert "MAX_CURRENT_PAGE_LENGTH = 200" in service


def test_export_client_validates_bytes_before_download():
    adapter = read("public/js/vetedge_report_provider_adapter.js")

    for expected in (
        "EdgeSuiteReportExport",
        "exports.normalizeOptions(options || {})",
        "exports.downloadVerified({ bytes, format: normalized.format, mime, filename })",
        'xhr.responseType = "arraybuffer"',
        'xhr.getResponseHeader("Content-Type")',
        'xhr.getResponseHeader("Content-Disposition")',
        '"/api/method/vetedge.services.report_export.download_report_export"',
    ):
        assert expected in adapter


def test_pdf_export_uses_same_server_rendering_path_for_report_exports():
    service = read("services/report_export.py")

    assert "_pdf_html(" in service
    assert "_pdf_bytes(" in service
    assert 'pdf_generator="chrome"' in service
    assert "return get_pdf(content, options=options)" in service
    assert 'thead{display:table-header-group}' in service


def test_legacy_pdf_patch_rejects_non_pdf_success_responses():
    patch = read("public/js/report_pdf_patch.js")

    for expected in (
        "EdgeSuiteReportExport",
        "shared.downloadVerified",
        'header.join(",") !== "37,80,68,70,45"',
        'preview.startsWith("<html")',
        'preview.startsWith("<!doctype html")',
        'mime && !String(mime).toLowerCase().includes("application/pdf")',
        'showError(error?.message || __("Report PDF download failed validation."))',
    ):
        assert expected in patch
