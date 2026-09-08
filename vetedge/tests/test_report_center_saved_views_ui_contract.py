from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "veterinary/page/vetedge_report_center/vetedge_report_center.js"


def test_report_center_wires_private_saved_view_endpoints_and_controls():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        "vetedge.services.report_saved_views.get_saved_report_views",
        "vetedge.services.report_saved_views.apply_saved_report_view",
        "vetedge.services.report_saved_views.save_report_view",
        "vetedge.services.report_saved_views.rename_saved_report_view",
        "vetedge.services.report_saved_views.delete_saved_report_view",
        "savedViews: []",
        "selectedSavedViewId",
        "savedViewOptions()",
        "loadSavedViews()",
        "applySavedView(viewId)",
        "promptSaveView(existing = null)",
        "deleteSelectedSavedView()",
        '__("Saved Views")',
        '__("Save View")',
        '__("Rename")',
        '__("Delete")',
    ):
        assert expected in source


def test_saved_view_application_revalidates_state_then_refreshes_provider_once():
    source = SOURCE.read_text(encoding="utf-8")
    method = source.split("async applySavedView(viewId)", 1)[1].split("promptSaveView", 1)[0]

    assert "frappe.call(SAVED_VIEWS_APPLY_API" in method
    assert "for (const key of REPORT_FILTER_KEYS)" in method
    assert "this.filters = nextFilters" in method
    assert "this.viewState = {" in method
    assert "visible_columns: normalizeReportColumnKeys(state.visible_columns)" in method
    assert "sort: normalizeReportSort(state.sort)" in method
    assert "this.pageStart = 0" in method
    assert "this.updateLocation()" in method
    assert "removed_filter_keys" in method
    assert "await this.refresh(true)" in method
    assert method.count("this.refresh(") == 1
    assert method.count("frappe.call(") == 1
    assert "provider.load" not in method


def test_manual_filter_column_or_sort_changes_clear_selected_saved_view_marker():
    source = SOURCE.read_text(encoding="utf-8")

    set_filter = source.split("setFilter(field, value)", 1)[1].split("reportFilters()", 1)[0]
    set_view_state = source.split("setViewState(state = {})", 1)[1].split("async applySavedView", 1)[0]

    assert 'this.selectedSavedViewId = ""' in set_filter
    assert 'this.selectedSavedViewId = ""' in set_view_state
    assert "const sortChanged" in set_view_state


def test_saved_view_ui_does_not_store_or_materialize_report_rows():
    source = SOURCE.read_text(encoding="utf-8")
    saved_view_methods = source.split("async loadSavedViews()", 1)[1].split("formatValue(value", 1)[0]

    assert "result.rows" not in saved_view_methods
    assert "provider.load" not in saved_view_methods
    assert "localStorage" not in saved_view_methods
    assert "sessionStorage" not in saved_view_methods
    assert "Make this my default view" not in saved_view_methods
