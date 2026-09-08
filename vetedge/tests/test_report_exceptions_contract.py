from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "services/report_exceptions.py"
OPERATIONS_UI = ROOT / "public/js/vetedge_hospitalisation_operations/VetEdgeHospitalisationOperations.vue"
REPORT_CENTER_UI = ROOT / "veterinary/page/vetedge_report_center/vetedge_report_center.js"


def test_hospitalisation_exceptions_are_bounded_advanced_and_read_only():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        '"hospitalisation_pending_stock"',
        '"hospitalisation_pending_billing"',
        '"hospitalisation_missing_price"',
        '"hospitalisation_operations"',
        "MAX_EXCEPTION_ITEMS = 50",
        "CANDIDATE_PARENT_WINDOW = 250",
        "CANDIDATE_CHILD_WINDOW = 500",
        "@frappe.read_only()",
        "check_advanced_reporting_entitlement()",
        'require_reporting_action(PENDING_ACTIONS_REPORT, "report", "view")',
        'frappe.has_permission(HOSPITALISATION_DOCTYPE, "read")',
        '"read_only": True',
    ):
        assert expected in source


def test_pending_stock_rule_reuses_existing_hospitalisation_stock_truth():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        '"stock_affecting": 1',
        '"stock_status": ["!=", "Posted"]',
        '"stock_entry": ["is", "not set"]',
        '"Stock-affecting Hospitalisation activities have not yet produced a Stock Entry."',
    ):
        assert expected in source


def test_new_exception_types_reuse_existing_billing_and_missing_price_truth():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        '"billable": 1',
        '"billing_status": ["not in", ["Charged", "Cancelled"]]',
        '"billing_status": ["not in", ["Invoiced", "Cancelled"]]',
        "qty = flt(row.get(\"qty\")) or 1",
        "rate = flt(row.get(\"rate\"))",
        "amount = flt(row.get(\"amount\")) or qty * rate",
        "if rate <= 0 or amount <= 0:",
        '"exception_type": "pending_billing"',
        '"exception_type": "missing_price"',
    ):
        assert expected in source


def test_child_candidates_are_intersected_through_permission_aware_parent_query():
    source = SOURCE.read_text(encoding="utf-8")

    assert "frappe.get_all(" in source
    assert "frappe.get_list(" in source
    assert "hospitalisation_operations._filters(filters)" in source
    assert "hospitalisation_operations._query_filters(report_filters)" in source
    assert 'query_filters["name"] = ["in", parent_names]' in source
    assert '"permission_intersection": "hospitalisation_get_list"' in source
    assert "frappe.get_doc(" not in source
    assert "ignore_permissions" not in source


def test_exception_feed_returns_clickable_source_reference_not_mutations():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        '"reference_doctype": HOSPITALISATION_DOCTYPE',
        '"reference_name": name',
        '"action_label": _("Open Hospitalisation")',
        '"tone": "warning"',
        '"tone": "danger"',
    ):
        assert expected in source

    for forbidden in (
        ".save(",
        ".submit(",
        ".cancel(",
        "frappe.db.set_value",
    ):
        assert forbidden not in source


def test_combined_operations_feed_is_one_browser_request_and_capped():
    source = SOURCE.read_text(encoding="utf-8")
    combined = source.split("def _hospitalisation_operations_exceptions", 1)[1].split("@frappe.whitelist()", 1)[0]

    assert "_hospitalisation_missing_price(filters)" in combined
    assert "_hospitalisation_pending_stock(filters)" in combined
    assert "_hospitalisation_pending_billing(filters)" in combined
    assert "items[:MAX_EXCEPTION_ITEMS]" in combined
    assert '"browser_request_count": 1' in combined
    assert '"included_types": ["missing_price", "pending_stock", "pending_billing"]' in combined


def test_hospitalisation_exception_panel_lives_in_operations_not_generic_report_center():
    operations = OPERATIONS_UI.read_text(encoding="utf-8")
    report_center = REPORT_CENTER_UI.read_text(encoding="utf-8")

    for expected in (
        "EdgeReportExceptionPanel",
        "vetedge.services.report_exceptions.get_report_exceptions",
        "hospitalisation_operations",
        "Pending Hospitalisation Actions",
        "advanced_features_entitled",
        '@open="openException"',
        "frappe.set_route('Form', item.reference_doctype, item.reference_name)",
    ):
        assert expected in operations

    assert "EdgeReportExceptionPanel" not in report_center
    assert "report_exceptions.get_report_exceptions" not in report_center


def test_exception_feed_uses_full_filtered_scope_and_does_not_follow_detail_pagination():
    source = OPERATIONS_UI.read_text(encoding="utf-8")
    refresh = source.split("async refreshOperationalView()", 1)[1].split("async fetchData()", 1)[0]
    exception = source.split("async fetchExceptions()", 1)[1].split("goToPage(page)", 1)[0]
    page_change = source.split("goToPage(page)", 1)[1].split("setPageSize(size)", 1)[0]

    assert "this.fetchExceptions()" in refresh
    assert "filters: JSON.stringify(this.requestFilters())" in exception
    assert "page_length" not in exception
    assert "currentPage" not in exception
    assert "fetchExceptions" not in page_change


def test_exception_feed_ignores_stale_filter_responses_and_skips_standard_plan_requests():
    source = OPERATIONS_UI.read_text(encoding="utf-8")
    exception = source.split("async fetchExceptions()", 1)[1].split("goToPage(page)", 1)[0]

    assert "if (!this.exceptionPanelSupported || !this.advancedExceptionsEntitled) return" in exception
    assert "const generation = ++this.exceptionRequestGeneration" in exception
    assert "const signature = this.exceptionRequestSignature()" in exception
    assert "generation !== this.exceptionRequestGeneration" in exception
    assert "signature !== this.exceptionRequestSignature()" in exception
    assert exception.index("generation !== this.exceptionRequestGeneration") < exception.index("this.exceptionPayload = payload || null")
