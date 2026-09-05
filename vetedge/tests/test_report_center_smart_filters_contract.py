from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_report_filter_search_is_bounded_permission_and_entitlement_aware():
    source = (ROOT / "services/report_filter_search.py").read_text(encoding="utf-8")
    for expected in (
        "MAX_PAGE_LENGTH = 20",
        "require_internal_user()",
        "validate_report_access(report_name)",
        'require_reporting_entitlement(report_name, scope_type="report")',
        "normalize_report_filters(report_name",
        'frappe.has_permission("Veterinary Patient", "read")',
        'frappe.has_permission("Customer", "read")',
        "get_assigned_branches",
        "user_has_global_branch_access",
        "get_veterinary_doctor_users",
        "get_vaccination_staff_users",
        'filters["primary_owner"] = owner',
        'filters["species"] = normalized.get("species")',
    ):
        assert expected in source
    assert "page_length = _bounded(page_length)" in source
    assert "ignore_permissions" not in source
    assert "LIMIT 500" not in source


def test_report_filter_ui_defines_workflow_specific_filters_without_user_master_search():
    source = (ROOT / "public/js/vetedge_report_filter_ui.js").read_text(encoding="utf-8")
    for report_name in (
        "Consultation Register",
        "Planned Treatment",
        "Lab Order Report",
        "Vaccination Report",
        "Patient Register",
        "Owner Register",
        "Service Revenue Breakdown",
    ):
        assert f'"{report_name}"' in source
    for expected in (
        'field: "patient"',
        'field: "customer"',
        'field: "practitioner"',
        'field: "consultation_type"',
        'field: "vaccine"',
        'field: "species"',
        'field: "breed"',
        'field: "outstanding_only"',
    ):
        assert expected in source
    assert 'doctype: "User"' not in source
    assert "limit_page_length: 500" not in source


def test_report_center_uses_cascading_server_smart_filter_runtime():
    source = (ROOT / "veterinary/page/vetedge_report_center/vetedge_report_center.js").read_text(encoding="utf-8")
    for expected in (
        'SMART_FILTER_API = "vetedge.services.report_filter_search.search_report_filter_options"',
        'frappe.require("/assets/vetedge/js/vetedge_report_filter_ui.js"',
        "window.VetEdgeReportFilterUI.hasSmartDefinition",
        "window.VetEdgeReportFilterUI.extraNodes",
        'page_length: 20',
        'if (field === "branch")',
        'this.filters.patient = ""',
        'this.filters.customer = ""',
        'this.filters.practitioner = ""',
        'if (field === "species") this.filters.breed = ""',
    ):
        assert expected in source
    assert "limit_page_length: 500" not in source
