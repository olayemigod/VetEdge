from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_hospitalisation_operations_is_permission_aware_paginated_and_page_enriched():
    source = (ROOT / "services/hospitalisation_operations.py").read_text(encoding="utf-8")

    for expected in (
        '@frappe.read_only()',
        'PAGE_LENGTH_MAX = 100',
        'OPERATIONAL_ACTIVE_STATUSES = {"Admitted", "Under Care", "Ready for Discharge"}',
        'normalize_report_filters("Active Hospitalisations", cleaned)',
        'frappe.has_permission(DOCTYPE, "read")',
        'page_length = min(max(cint(page_length) or 50, 1), PAGE_LENGTH_MAX)',
        'parents = _page_rows(query_filters, start, page_length)',
        'filters={"parent": ["in", parent_names]}',
        '"child_scope": "requested_parent_page_only"',
        '"all_matching_rows_materialized": False',
    ):
        assert expected in source

    assert "frappe.get_doc(" not in source
    assert "ignore_permissions" not in source


def test_hospitalisation_operations_does_not_duplicate_mutation_workflows():
    source = (ROOT / "services/hospitalisation_operations.py").read_text(encoding="utf-8")
    for forbidden in (
        ".save(",
        ".insert(",
        ".submit(",
        ".cancel(",
        "frappe.db.set_value",
        "frappe.delete_doc",
        "Stock Entry",
        "create_invoice",
    ):
        assert forbidden not in source
