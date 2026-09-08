from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "veterinary/page/vetedge_report_center/vetedge_report_center.js"


def test_report_center_uses_shareable_url_column_and_sort_view_state():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        "function normalizeReportColumnKeys(value)",
        "function normalizeReportSort(value = null)",
        'columns: get("columns")',
        'sort: get("sort")',
        "visible_columns: normalizeReportColumnKeys(initial.columns)",
        "sort: normalizeReportSort(initial.sort)",
        'params.set("columns", visibleColumns.join(","))',
        'params.set("sort", `${sort.field}:${sort.direction}`)',
        "columnChooserEnabled: true",
        "viewState: this.viewState",
        "sort: normalizeReportSort(this.viewState?.sort)",
        "onViewStateChange: this.setViewState",
        "filters, columns and sort retained in URL",
    ):
        assert expected in source


def test_column_only_view_state_change_remains_presentation_only_but_sort_reloads_from_page_one():
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index("\t\t\t\tsetViewState(state = {})")
    end = source.index("\t\t\t\tasync applySavedView", start)
    block = source[start:end]

    for expected in (
        "const previousSort = normalizeReportSort(this.viewState?.sort);",
        "const nextSort = normalizeReportSort(state.sort);",
        "const sortChanged = JSON.stringify(previousSort) !== JSON.stringify(nextSort);",
        "this.updateLocation();",
        "if (!sortChanged) return;",
        "this.pageStart = 0;",
        "this.refresh();",
    ):
        assert expected in block

    assert block.index("if (!sortChanged) return;") < block.index("this.refresh();")
    assert "provider.load" not in block
    assert "frappe.call" not in block
    assert "frappe.db" not in block
    assert "localStorage" not in block
    assert "sessionStorage" not in block


def test_report_provider_load_receives_current_sort_after_filters_and_pagination():
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index("\t\t\t\tasync refresh(resetPage = false)")
    end = source.index("\t\t\t\tgoToPage(pageNumber)", start)
    block = source[start:end]

    assert "this.result = await provider.load({" in block
    assert "filters: this.reportFilters()," in block
    assert "start: this.pageStart," in block
    assert "page_length: this.pageLength," in block
    assert "sort: normalizeReportSort(this.viewState?.sort)," in block
