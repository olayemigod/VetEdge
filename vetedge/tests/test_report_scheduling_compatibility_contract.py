from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "services/report_scheduling_compatibility.py"


def test_scheduling_reuses_frappe_auto_email_instead_of_creating_second_scheduler():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        'NATIVE_AUTO_EMAIL = "native_auto_email"',
        'VETEDGE_EXPORT_ADAPTER = "vetedge_export_adapter"',
        'NOT_SCHEDULABLE = "not_schedulable"',
        'frappe.db.exists("DocType", "Auto Email Report")',
        '"scheduler_reused": "Frappe Auto Email Report"',
        '"custom_scheduler_created": False',
        '"write_performed": False',
        '@frappe.read_only()',
    ):
        assert expected in source

    for forbidden in (
        "scheduler_events",
        "frappe.enqueue(",
        "frappe.sendmail(",
        ".insert(",
        ".save(",
        "frappe.db.set_value",
    ):
        assert forbidden not in source


def test_optimized_edgesuite_provider_reports_require_vetedge_export_adapter():
    source = SOURCE.read_text(encoding="utf-8")

    for report in (
        '"Consultation Register"',
        '"Planned Treatment"',
        '"Lab Order Report"',
        '"Vaccination Report"',
        '"Patient Register"',
        '"Owner Register"',
        '"Stock Expiry Status"',
    ):
        assert report in source.split("VETEDGE_PROVIDER_REPORTS", 1)[1].split("REPORT_ALIASES", 1)[0]

    assert '"delivery_mode": VETEDGE_EXPORT_ADAPTER' in source
    assert '"reason_code": "VETEDGE_PROVIDER_SEMANTICS"' in source


def test_native_reports_only_use_auto_email_when_both_native_report_and_scheduler_exist():
    source = SOURCE.read_text(encoding="utf-8")
    classify = source.split("def classify_report", 1)[1].split("def get_report_scheduling_compatibility", 1)[0]

    assert "native_report = _native_report_exists(name)" in classify
    assert "auto_email = _auto_email_available()" in classify
    assert "if native_report and auto_email:" in classify
    assert '"delivery_mode": NATIVE_AUTO_EMAIL' in classify
    assert '"reason_code": "NATIVE_SCHEDULER_CONTRACT_UNAVAILABLE"' in classify


def test_scheduled_delivery_remains_permission_and_advanced_feature_aware():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        "validate_report_access(name, user=user)",
        'get_reporting_entitlement(name, scope_type="report", user=user)',
        "check_advanced_reporting_entitlement(user=user)",
        '"scheduled_delivery_entitled": bool(advanced.get("allowed"))',
        '"scheduled_delivery_feature_key": advanced.get("feature_key") or "advanced_reports"',
        '"can_configure": bool(classification.get("schedulable") and entitlement.get("entitled") and advanced.get("allowed"))',
        "require_internal_user()",
    ):
        assert expected in source


def test_aliases_resolve_to_canonical_vetedge_report_keys():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        '"Laboratory Report": "Lab Order Report"',
        '"Stock Expiry Report": "Stock Expiry Status"',
        '"Stock Expiry Monitor": "Stock Expiry Status"',
        '"Planned Treatment Report": "Planned Treatment"',
        "return REPORT_ALIASES.get(name, name)",
    ):
        assert expected in source
