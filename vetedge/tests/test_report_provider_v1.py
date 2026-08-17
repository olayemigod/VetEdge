from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"


def read(path: str) -> str:
    return (APP / path).read_text()


def test_report_center_prefers_provider_runtime_and_keeps_query_report_fallback():
    center = read("veterinary/page/vetedge_report_center/vetedge_report_center.js")
    adapter = read("public/js/vetedge_report_provider_adapter.js")

    assert "VetEdgeReportProviders" in center
    assert "getProvider?.(this.reportName)" in center
    assert "ensureQueryProvider?.(this.reportName, this.reportName)" in center
    assert 'method: "frappe.desk.query_report.run"' in adapter
    assert "ignore_prepared_report: 1" in adapter
    assert "ignore_user_permissions: 0" in center


def test_report_center_uses_shared_export_builder_print_and_same_desk_navigation():
    center = read("veterinary/page/vetedge_report_center/vetedge_report_center.js")

    for expected in (
        '"EdgeReportExportDialog"',
        "downloadReportExport",
        '__("Download / Export")',
        '__("Print")',
        "printReport",
        "printBusy",
        "exportOpen",
        "exportBusy",
        "onExport: this.runExport",
        'scope: "all_filtered"',
        'typeof frappe.set_route === "function"',
        "frappe.set_route(...parts)",
        'date_preset: get("date_preset")',
    ):
        assert expected in center


def test_stock_expiry_is_registered_as_query_level_paginated_reference():
    registry = read("public/js/vetedge_report_provider_registry.js")

    assert 'registerPaginatedProvider("Stock Expiry Report"' in registry
    assert "get_stock_expiry_data" in registry
    assert 'pagination_mode: "query-level"' in registry
    assert "limit: pageLength" in registry
    assert "offset: start" in registry
    assert "maxPageLength: 100" in registry


def test_planned_treatment_uses_query_level_detail_pagination_with_scoped_parents():
    registry = read("public/js/vetedge_report_provider_registry.js")
    service = read("services/treatment_plan_report.py")
    center = read("veterinary/page/vetedge_report_center/vetedge_report_center.js")

    assert 'registerPaginatedProvider("Planned Treatment"' in registry
    assert 'pagination_mode": "query-level-detail"' in service
    assert 'parent_scope_mode": "scoped-consultations"' in service
    assert "limit_start=start" in service
    assert "limit_page_length=page_length" in service
    assert "def _aggregate_treatments(" in service
    assert "COUNT(*) AS `total`" in service
    assert "SUM(" in service
    assert 'group = " GROUP BY `parent`" if group_by_parent else ""' in service
    assert "patient_totals" in service
    assert '"query-level-detail"' in center


def test_lab_order_provider_is_permission_scoped_query_paginated_and_aggregate_backed():
    service = read("services/lab_order_report.py")
    registry = read("public/js/vetedge_report_provider_registry.js")

    for expected in (
        'normalize_report_filters("Lab Order Report", cleaned)',
        "require_internal_user()",
        'frappe.has_permission(DOCTYPE, "read")',
        'owner = report_filters.get("owner") or report_filters.get("customer")',
        "limit_start=start",
        "limit_page_length=page_length",
        "frappe.db.count(DOCTYPE, filters=query_filters)",
        "def _status_counts(query_filters: dict)",
        'unbilled_filters["linked_invoice"] = ("is", "not set")',
        '"detail_rows_materialized": False',
        '"summary_mode": "aggregate"',
        'filters={"parent": ("in", names), "entered_on": ("is", "set")}',
    ):
        assert expected in service

    assert '"Lab Order Report"' in registry
    assert "vetedge.services.lab_order_report.get_lab_order_report_view" in registry


def test_vaccination_provider_pushes_due_filter_and_pagination_to_database():
    service = read("services/vaccination_report.py")
    registry = read("public/js/vetedge_report_provider_registry.js")

    for expected in (
        'normalize_report_filters("Vaccination Report", cleaned)',
        "require_internal_user()",
        'frappe.has_permission(DOCTYPE, "read")',
        'owner = report_filters.get("owner") or report_filters.get("customer")',
        "limit_start=start",
        "limit_page_length=page_length",
        'filters["next_due_date"] = ("between", [today, add_days(today, 30)])',
        'filters["next_due_date"] = ("<", today)',
        '"due_filter_mode": "database"',
        '"detail_rows_materialized": False',
        '"summary_mode": "aggregate"',
    ):
        assert expected in service

    assert '"Vaccination Report"' in registry
    assert "vetedge.services.vaccination_report.get_vaccination_report_view" in registry


def test_new_clinical_report_providers_are_read_only_and_do_not_mutate_workflows():
    lab = read("services/lab_order_report.py")
    vaccination = read("services/vaccination_report.py")

    for service in (lab, vaccination):
        assert "@frappe.read_only()" in service
        for forbidden in ("ignore_permissions", ".submit()", ".cancel()", "frappe.db.set_value", ".save("):
            assert forbidden not in service


def test_interactive_provider_contract_stays_read_only_and_export_separate():
    adapter = read("public/js/vetedge_report_provider_adapter.js")
    registry = read("public/js/vetedge_report_provider_registry.js")

    for forbidden in ("ignore_permissions", ".submit()", ".cancel()", "frappe.db.set_value"):
        assert forbidden not in adapter
        assert forbidden not in registry

    assert "export: null" in adapter
    assert "export: null" in registry
    assert "page_length" in adapter
    assert "page_length" in registry
