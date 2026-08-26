from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "services/report_scheduling.py"


def test_schedule_management_is_owner_scoped_and_vetedge_marked():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        'DESCRIPTION_PREFIX = "Scheduled VetEdge report: "',
        'filters = {"user": frappe.session.user, "description": ["like", f"{DESCRIPTION_PREFIX}%"]}',
        "def _owned_vetedge_schedule(name: str):",
        "doc.user != frappe.session.user",
        "startswith(DESCRIPTION_PREFIX)",
    ):
        assert expected in source


def test_owner_can_list_disable_and_delete_without_cross_user_bypass():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        "def get_my_report_schedules(",
        "frappe.get_list(",
        "page_length=100",
        "def set_report_schedule_enabled(",
        'doc.check_permission("write")',
        "doc.save()",
        "def delete_report_schedule(",
        'doc.check_permission("delete")',
        "doc.delete()",
    ):
        assert expected in source

    for forbidden in (
        "ignore_permissions=True",
        "frappe.db.set_value",
        "frappe.delete_doc(",
    ):
        assert forbidden not in source


def test_plan_downgrade_does_not_prevent_owner_from_stopping_existing_schedule():
    source = SOURCE.read_text(encoding="utf-8")
    disable = source.split("def set_report_schedule_enabled", 1)[1].split("def delete_report_schedule", 1)[0]
    delete = source.split("def delete_report_schedule", 1)[1]

    assert "get_report_scheduling_compatibility" not in disable
    assert "get_report_scheduling_compatibility" not in delete
    assert "advanced_reports" not in disable
    assert "advanced_reports" not in delete
