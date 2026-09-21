from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "services/report_grouping.py"


def test_consultation_grouping_is_advanced_aggregate_only_and_bounded():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        'SUPPORTED_REPORT = "Consultation Register"',
        "MAX_GROUPS = 50",
        '"branch": {"field": "service_branch"',
        '"practitioner": {"field": "consulting_practitioner"',
        '"consultation_type": {"field": "consultation_type"',
        '"status": {"field": "status"',
        "require_reporting_action(report_name, \"report\", \"view\")",
        "check_advanced_reporting_entitlement()",
        '"aggregate_only": True',
        '"detail_rows_materialized": False',
        '"group_limit": MAX_GROUPS',
    ):
        assert expected in source


def test_grouping_reuses_consultation_scope_and_does_not_materialize_detail_rows():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        "consultation_report._filters",
        "consultation_report._query_filters",
        "consultation_report._where_clause",
        "consultation_report._require_read_permission",
        "GROUP BY c.`{field}`",
        "LIMIT %(limit)s",
    ):
        assert expected in source

    for forbidden in (
        "get_consultation_register_view(",
        "_page_rows(",
        "frappe.get_doc(",
        "provider.load",
    ):
        assert forbidden not in source


def test_grouping_planned_value_join_is_filter_selective_not_global_child_materialization():
    source = SOURCE.read_text(encoding="utf-8")

    assert "LEFT JOIN `tabPlanned Treatment Item` pt" in source
    assert "pt.`parent` = c.`name`" in source
    assert "COUNT(DISTINCT c.`name`)" in source
    assert "COUNT(DISTINCT CASE WHEN c.`status` = 'Completed'" in source
    assert '"planned_value_mode": "filtered_child_join"' in source
    assert "SELECT\n\t\t\t\t\tpt.`parent`" not in source
