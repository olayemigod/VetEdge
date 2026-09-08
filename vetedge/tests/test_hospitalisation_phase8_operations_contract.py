from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_hospitalisation_operations_provider_is_paginated_and_read_only():
    source = (ROOT / "services/hospitalisation_operations.py").read_text(encoding="utf-8")

    for expected in (
        "@frappe.read_only()",
        "PAGE_LENGTH_MAX = 100",
        'OPERATIONAL_ACTIVE_STATUSES = {"Admitted", "Under Care", "Ready for Discharge"}',
        "frappe.get_list(",
        'filters={"parent": ["in", parent_names]}',
        '"pagination_mode": "query-level-parent-page-child-enrichment"',
        '"all_matching_rows_materialized": False',
        '"child_scope": "requested_parent_page_only"',
    ):
        assert expected in source

    assert '"Draft"' not in source.split("OPERATIONAL_ACTIVE_STATUSES", 1)[1].split("\n", 1)[0]
    assert "frappe.get_doc(" not in source
    assert "ignore_permissions" not in source
    assert "frappe.db.set_value" not in source
    assert ".save()" not in source


def test_hospitalisation_filter_search_is_bounded_and_uses_visible_parent_records():
    source = (ROOT / "services/hospitalisation_filter_search.py").read_text(encoding="utf-8")

    for expected in (
        "MAX_PAGE_LENGTH = 20",
        "CANDIDATE_WINDOW = 60",
        'FIELDS = {"branch", "patient", "customer", "practitioner", "care_location"}',
        'normalize_report_filters("Active Hospitalisations"',
        "frappe.get_list(",
        "group_by=fieldname",
        "page_length=CANDIDATE_WINDOW",
        "frappe.has_permission(DOCTYPE, \"read\")",
        "@frappe.read_only()",
    ):
        assert expected in source

    assert "ignore_permissions" not in source
    assert "page_length=500" not in source


def test_hospitalisation_operations_uses_edgesuite_report_shell_without_mutation_actions():
    component = (
        ROOT / "public/js/vetedge_hospitalisation_operations/VetEdgeHospitalisationOperations.vue"
    ).read_text(encoding="utf-8")
    bundle = (ROOT / "public/js/vetedge_hospitalisation_operations.bundle.js").read_text(encoding="utf-8")
    page = (
        ROOT
        / "veterinary/page/vetedge_hospitalisation_operations/vetedge_hospitalisation_operations.js"
    ).read_text(encoding="utf-8")

    for expected in (
        "<EdgeAppShell",
        "<EdgeReportShell",
        "<EdgeLinkField",
        "<EdgeDropdown",
        "<EdgeInput",
        ":exportEnabled=\"false\"",
        ":printEnabled=\"false\"",
        "search_hospitalisation_filter_options",
        "get_hospitalisation_operations",
        "this.filters.patient = ''",
        "this.filters.customer = ''",
        "this.filters.practitioner = ''",
        "this.filters.care_location = ''",
        "Math.min(100",
    ):
        assert expected in component

    assert "applyWorkspaceSafety" in bundle
    assert "mountVetEdgeHospitalisationOperations" in bundle
    assert "edgeui.bundle.js" in page
    assert "vetedge_hospitalisation_operations.bundle.js" in page

    for forbidden in (
        "admit_hospitalisation",
        "generate_hospitalisation_daily_charges",
        "post_hospitalisation",
        "discharge_hospitalisation",
        "create_invoice",
        "submit_invoice",
        "frappe.db.set_value",
    ):
        assert forbidden not in component


def test_sidebar_sync_replaces_retired_dashboard_with_operations_page():
    source = (ROOT / "install/dashboard.py").read_text(encoding="utf-8")
    page_json = (
        ROOT
        / "veterinary/page/vetedge_hospitalisation_operations/vetedge_hospitalisation_operations.json"
    ).read_text(encoding="utf-8")

    for expected in (
        'HOSPITALISATION_OPERATIONS_PAGE = "vetedge-hospitalisation-operations"',
        'RETIRED_HOSPITALISATION_DASHBOARD_PAGE = "veterinary-hospitalisation-dashboard"',
        "_replace_retired_hospitalisation_dashboard",
        '"label": "Hospitalisation Operations"',
        '"link_to": HOSPITALISATION_OPERATIONS_PAGE',
        '("veterinary", "page", "vetedge_hospitalisation_operations", "vetedge_hospitalisation_operations.json")',
    ):
        assert expected in source

    assert '"name": "vetedge-hospitalisation-operations"' in page_json
    assert '"title": "Hospitalisation Operations"' in page_json
