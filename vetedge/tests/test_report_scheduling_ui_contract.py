from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "public/js/vetedge_report_scheduling_ui.js"
PDF_PATCH = ROOT / "public/js/report_pdf_patch.js"


def test_report_center_scheduling_ui_uses_shared_edgesuite_dialog_and_server_compatibility():
    source = UI.read_text(encoding="utf-8")

    for expected in (
        "EdgeReportScheduleDialog",
        "get_scheduling_compatibility",
        'compatibility.delivery_mode === "vetedge_export_adapter"',
        "create_vetedge_report_schedule",
        "create_native_report_schedule",
        "JSON.stringify(state.filters)",
        "JSON.stringify(options.columns || state.columns || [])",
    ):
        assert expected in source


def test_scheduling_ui_does_not_poll_or_hook_report_refresh_provider():
    source = UI.read_text(encoding="utf-8")

    assert "setInterval(" not in source
    assert "provider.load" not in source
    assert "reportFilters()" not in source
    assert "MutationObserver" in source
    assert "getCompatibility(state.reportName)" in source


def test_user_schedule_management_uses_owned_server_endpoints():
    source = UI.read_text(encoding="utf-8")

    for expected in (
        "get_my_report_schedules",
        "set_report_schedule_enabled",
        "delete_report_schedule",
        '__("My Scheduled Reports")',
        '__("Pause")',
        '__("Enable")',
        '__("Delete")',
    ):
        assert expected in source


def test_scheduling_ui_is_loaded_from_existing_global_report_asset():
    source = PDF_PATCH.read_text(encoding="utf-8")

    assert 'frappe.require("/assets/vetedge/js/vetedge_report_scheduling_ui.js")' in source
