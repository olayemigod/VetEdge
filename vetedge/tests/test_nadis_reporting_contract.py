from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_nadis_vaccination_source_is_paginated_read_only_and_branch_safe():
    source = (ROOT / "services/nadis_reporting.py").read_text(encoding="utf-8")

    for expected in (
        '@frappe.read_only()',
        'normalize_report_filters("Vaccination Report", cleaned)',
        'frappe.has_permission(VACCINATION_DOCTYPE, "read")',
        'frappe.has_permission(PATIENT_DOCTYPE, "read")',
        'PAGE_LENGTH_MAX = 100',
        'page_length = min(max(cint(page_length) or 50, 1), PAGE_LENGTH_MAX)',
        'start=start',
        'page_length=page_length',
        '"pagination_mode": "query-level"',
        '"detail_rows_materialized": False',
        '"template_mapping_verified": False',
        '"submission_ready": False',
    ):
        assert expected in source

    for forbidden in (
        "ignore_permissions",
        "frappe.db.set_value",
        ".submit()",
        ".cancel()",
        "frappe.delete_doc",
    ):
        assert forbidden not in source


def test_nadis_vaccination_source_covers_existing_regulatory_facts_without_guessing_template_columns():
    source = (ROOT / "services/nadis_reporting.py").read_text(encoding="utf-8")

    for fieldname in (
        '"vaccination_record"',
        '"administered_on"',
        '"service_branch"',
        '"company"',
        '"patient"',
        '"patient_name"',
        '"owner"',
        '"species"',
        '"breed"',
        '"vaccine"',
        '"dose"',
        '"route"',
        '"batch_no"',
        '"batch_expiry_date"',
        '"administered_by"',
        '"status"',
        '"next_due_date"',
    ):
        assert fieldname in source

    assert "final official NADIS workbook" in source
