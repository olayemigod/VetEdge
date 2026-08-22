from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"


def read(path: str) -> str:
    return (APP / path).read_text(encoding="utf-8")


def test_stock_expiry_interactive_sorting_is_allowlisted_before_pagination():
    source = read("services/stock_expiry_interactive.py")

    for expected in (
        "SORT_FIELDS = {",
        '"item_code": "item_code"',
        '"item_name": "item_name"',
        '"batch_no": "batch_no"',
        '"warehouse": "warehouse"',
        '"qty": "qty"',
        '"expiry_date": "expiry_date"',
        '"days_to_expiry": "DATEDIFF(expiry_date, %(today)s)"',
        '"expiry_status": "expiry_status"',
        'DEFAULT_SORT = {"field": "expiry_date", "direction": "asc"}',
        'field not in SORT_FIELDS or direction not in {"asc", "desc"}',
        "order_by = _order_by(normalized_sort)",
        "ORDER BY {order_by}",
        "LIMIT %(limit)s OFFSET %(offset)s",
        '"sorting_mode": "server-allowlist"',
        '"sort": normalized_sort',
    ):
        assert expected in source

    assert '"branch"' not in source.split("SORT_FIELDS = {", 1)[1].split("}", 1)[0]


def test_stock_expiry_provider_exposes_only_database_sortable_columns():
    registry = read("public/js/vetedge_report_provider_registry.js")

    for field in (
        "item_code",
        "item_name",
        "batch_no",
        "warehouse",
        "qty",
        "stock_uom",
        "expiry_date",
        "days_to_expiry",
        "expiry_status",
    ):
        assert f'fieldname: "{field}"' in registry

    assert '{ fieldname: "branch", label: "Branch", fieldtype: "Link", options: "Branch", sortable: false }' in registry
    assert 'function stockFilters(filters = {}, start = 0, pageLength = 50, sort = null)' in registry
    assert 'loadPage: async ({ filters = {}, start = 0, page_length = 50, sort = null })' in registry
    assert '{ filters: stockFilters(filters, start, page_length, sort) }' in registry
    assert 'sorting_mode: payload.metadata?.sorting_mode || "server-allowlist"' in registry
