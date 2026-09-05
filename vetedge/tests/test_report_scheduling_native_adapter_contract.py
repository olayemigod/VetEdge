from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "services/report_scheduling.py"


def test_native_schedule_adapter_reuses_auto_email_report_and_fails_closed_for_vetedge_provider_reports():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        'AUTO_EMAIL_DOCTYPE = "Auto Email Report"',
        "get_report_scheduling_compatibility(report_name)",
        'compatibility.get("delivery_mode") != NATIVE_AUTO_EMAIL',
        '_("This report uses VetEdge reporting semantics and requires the VetEdge scheduled-export adapter.")',
        'frappe.has_permission(AUTO_EMAIL_DOCTYPE, "create")',
        '"doctype": AUTO_EMAIL_DOCTYPE',
        '"user": frappe.session.user',
        "doc.insert()",
    ):
        assert expected in source

    for forbidden in (
        "scheduler_events",
        "frappe.enqueue(",
        "frappe.sendmail(",
        "ignore_permissions=True",
    ):
        assert forbidden not in source


def test_schedule_filters_are_branch_permission_normalized_before_persistence():
    source = SOURCE.read_text(encoding="utf-8")

    assert "normalize_report_filters(compatibility[\"report_name\"], _parse_filters(filters))" in source
    assert '"filters": json.dumps(filters, default=str, sort_keys=True)' in source
    assert "ignore_permissions" not in source


def test_schedule_input_is_bounded_and_validated():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        'ALLOWED_FREQUENCIES = {"Daily", "Weekdays", "Weekly", "Monthly"}',
        'ALLOWED_FORMATS = {"HTML", "XLSX", "CSV", "PDF"}',
        "MAX_SCHEDULE_ROWS = 5000",
        "validate_email_address(token.strip(), throw=True)",
        "if frequency == \"Weekly\"",
        "row_limit = min(max(cint(no_of_rows) or 500, 1), MAX_SCHEDULE_ROWS)",
    ):
        assert expected in source


def test_schedule_creation_requires_advanced_entitlement_through_compatibility_contract():
    source = SOURCE.read_text(encoding="utf-8")

    assert 'if not compatibility.get("can_configure"):' in source
    assert '_("Scheduled report delivery is not available for this report or current Plan.")' in source
    assert "require_internal_user()" in source
