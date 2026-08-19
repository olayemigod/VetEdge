from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "services/report_exceptions.py"


def test_hospitalisation_pending_stock_exception_is_bounded_advanced_and_read_only():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        'SUPPORTED_EXCEPTION_KEYS = {"hospitalisation_pending_stock"}',
        "MAX_EXCEPTION_ITEMS = 50",
        "CANDIDATE_PARENT_WINDOW = 250",
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
    ):
        assert expected in source

    for forbidden in (
        ".save(",
        ".submit(",
        ".cancel(",
        "frappe.db.set_value",
    ):
        assert forbidden not in source
