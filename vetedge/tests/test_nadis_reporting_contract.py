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
        '"template_mapping_verified": True',
        '"submission_ready": False',
        'validate_nadis_vaccination_export',
        'download_nadis_vaccination_workbook',
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


def test_nadis_vaccination_source_covers_existing_regulatory_facts():
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
        '"vaccination_reason"',
        '"dose"',
        '"route"',
        '"batch_no"',
        '"batch_expiry_date"',
        '"administered_by"',
        '"status"',
        '"next_due_date"',
    ):
        assert fieldname in source

    assert "supplied official NADIS workbook schema" in source


def test_official_vaccination_template_mapping_matches_supplied_workbook_contract():
    template = (ROOT / "services/nadis_templates.py").read_text(encoding="utf-8")
    export = (ROOT / "services/nadis_vaccination_export.py").read_text(encoding="utf-8")

    for expected in (
        'VACCINATION_TEMPLATE_FILENAME = "Nadis Template Vaccination Report 1.xlsx"',
        'VACCINATION_TEMPLATE_SHA256 = "458e7af8b47c491f5245f5fc6cc8bbe754bbc23ab63829e88bb2083b813c05ba"',
        'VACCINATION_SHEET = "Vaccinations"',
        'VACCINATION_TITLE = "Monthly Vaccination Report"',
        'VACCINATION_DATA_START_ROW = 5',
        '"Country * "',
        '"Admin Division (Level 1) * "',
        '"Reason for the vaccination * "',
        '"Number of animals vaccinated for the species selected * "',
        '"Vaccine tested at PANVAC"',
    ):
        assert expected in template

    for expected in (
        'query_filters["status"] = "Administered"',
        'BRANCH_NADIS_ADMIN_LEVEL_1_FIELD',
        'BRANCH_NADIS_ADMIN_LEVEL_2_FIELD',
        '"nadis_species"',
        '"nadis_disease"',
        '"nadis_vaccine_type"',
        '"nadis_source_of_vaccine"',
        '"nadis_panvac_tested"',
        '"vaccination_reason"',
        'MAX_TEMPLATE_DATA_ROWS = 235',
        '"template_mapping_verified": True',
        '"submission_ready": not validation["errors"] and bool(aggregated)',
        'frappe.local.response.type = "binary"',
    ):
        assert expected in export

    for forbidden in (
        "ignore_permissions",
        "frappe.db.set_value",
        ".submit()",
        ".cancel()",
        "frappe.delete_doc",
    ):
        assert forbidden not in export


def test_regulatory_fields_live_on_the_correct_operational_masters():
    species = (ROOT / "veterinary/doctype/veterinary_species/veterinary_species.json").read_text(encoding="utf-8")
    vaccine = (ROOT / "veterinary/doctype/veterinary_vaccine/veterinary_vaccine.json").read_text(encoding="utf-8")
    vaccination = (ROOT / "veterinary/doctype/veterinary_vaccination_record/veterinary_vaccination_record.json").read_text(encoding="utf-8")
    custom_fields = (ROOT / "install/custom_fields.py").read_text(encoding="utf-8")

    assert '"fieldname": "nadis_species"' in species
    for fieldname in (
        "nadis_disease",
        "nadis_vaccine_type",
        "nadis_source_of_vaccine",
        "nadis_panvac_tested",
    ):
        assert f'"fieldname": "{fieldname}"' in vaccine
    assert '"fieldname": "vaccination_reason"' in vaccination
    assert 'BRANCH_NADIS_ADMIN_LEVEL_1_FIELD = "vetedge_nadis_admin_level_1"' in custom_fields
    assert 'BRANCH_NADIS_ADMIN_LEVEL_2_FIELD = "vetedge_nadis_admin_level_2"' in custom_fields
