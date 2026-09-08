from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"


def read(path: str) -> str:
    return (APP / path).read_text(encoding="utf-8")


def test_lab_order_sorting_is_server_allowlisted_and_stable():
    source = read("services/lab_order_report.py")

    for expected in (
        'SORT_FIELDS = {',
        '"lab_order": "name"',
        '"owner": "primary_owner"',
        '"service_branch": "service_branch"',
        '"status": "status"',
        '"requested_on": "requested_on"',
        '"reviewed_on": "doctor_reviewed_on"',
        'DEFAULT_SORT = {"field": "requested_on", "direction": "desc"}',
        'field not in SORT_FIELDS or direction not in {"asc", "desc"}',
        'return f"{source} {direction}, name {direction}"',
        'order_by=_order_by(normalized_sort)',
        '"sorting_mode": "server-allowlist"',
        '"sort": normalized_sort',
    ):
        assert expected in source

    for forbidden in (
        "ignore_permissions",
        "frappe.db.set_value",
        ".submit()",
        ".cancel()",
    ):
        assert forbidden not in source


def test_lab_order_page_enriched_result_timestamp_is_not_claimed_sortable():
    source = read("services/lab_order_report.py")

    assert '"fieldname": "result_entered_on", "label": _("Result Entered On")' in source
    assert 'column["sortable"] = column.get("fieldname") in SORT_FIELDS' in source
    sort_fields = source.split("SORT_FIELDS = {", 1)[1].split("}", 1)[0]
    assert '"result_entered_on"' not in sort_fields


def test_lab_order_provider_passes_shared_sort_contract_and_preserves_alias():
    registry = read("public/js/vetedge_report_provider_registry.js")

    for expected in (
        "function registerLabOrderReport()",
        'loadPage: async ({ filters = {}, start = 0, page_length = 50, sort = null })',
        '"vetedge.services.lab_order_report.get_lab_order_report_view"',
        "sort,",
        'sorting_mode: payload.metadata?.sorting_mode || "server-allowlist"',
        'reports.registerProvider("Laboratory Report", provider)',
        "registerLabOrderReport();",
    ):
        assert expected in registry

    generic_start = registry.index("function registerServerPaginatedReport")
    generic_end = registry.index("function registerClinicalReports", generic_start)
    generic = registry[generic_start:generic_end]
    assert "sort = null" not in generic
    assert "columns: nonSortableColumns(payload.columns)" in generic
