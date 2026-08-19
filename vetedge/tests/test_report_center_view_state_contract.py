from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "veterinary/page/vetedge_report_center/vetedge_report_center.js"


def test_report_center_uses_shareable_url_column_view_state():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        "function normalizeReportColumnKeys(value)",
        'columns: get("columns")',
        "viewState: { visible_columns: normalizeReportColumnKeys(initial.columns) }",
        'params.set("columns", visibleColumns.join(","))',
        "columnChooserEnabled: true",
        "viewState: this.viewState",
        "onViewStateChange: this.setViewState",
        "filters and columns retained in URL",
    ):
        assert expected in source


def test_column_view_state_change_is_presentation_only():
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index("\t\t\t\tsetViewState(state = {})")
    end = source.index("\t\t\t\tformatValue", start)
    block = source[start:end]

    assert "this.updateLocation();" in block
    assert "this.refresh(" not in block
    assert "provider.load" not in block
    assert "frappe.call" not in block
    assert "frappe.db" not in block
    assert "localStorage" not in block
    assert "sessionStorage" not in block
