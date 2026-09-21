from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "services/report_comparison.py"
CAPABILITIES = ROOT / "services/reporting_capabilities.py"


def test_consultation_comparison_is_aggregate_only_and_equal_period():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        'SUPPORTED_REPORTS = {"Consultation Register"}',
        "DEFAULT_PERIOD_DAYS = 30",
        "comparison_to = getdate(add_days(current_from, -1))",
        "comparison_from = getdate(add_days(comparison_to, -(period_days - 1)))",
        "consultation_report._count_rows",
        "consultation_report._status_counts",
        "consultation_report._planned_total",
        "consultation_report._follow_up_count",
        '"comparison_mode": "previous_equal_period"',
        '"aggregate_only": True',
        '"detail_rows_materialized": False',
    ):
        assert expected in source

    for forbidden in (
        "_page_rows(",
        "_render_rows(",
        "frappe.get_all(",
        "frappe.get_list(",
        "provider.load",
    ):
        assert forbidden not in source


def test_comparison_requires_advanced_reporting_feature_even_for_standard_report():
    source = SOURCE.read_text(encoding="utf-8")
    capabilities = CAPABILITIES.read_text(encoding="utf-8")

    assert 'capabilities = require_reporting_action(report_name, "report", "view")' in source
    assert 'capabilities.get("advanced_features_entitled")' in source
    assert "Advanced Reporting Access Required" in source
    assert "check_advanced_reporting_entitlement" in capabilities
    assert '"advanced_features_entitled"' in capabilities
    assert '"advanced_features_source"' in capabilities
    assert '"advanced_features_reason_code"' in capabilities


def test_comparison_metrics_are_server_supplied_with_direction_semantics():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        '"total_consultations"',
        '"completed"',
        '"completion_rate"',
        '"average_planned_value"',
        '"follow_up_required"',
        '"cancelled"',
        '"delta_percent"',
        '"delta_tone"',
        "positive_is_good=True",
        "positive_is_good=False",
    ):
        assert expected in source
