from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "services/report_saved_views.py"


def test_private_saved_views_use_frappe_user_settings_without_new_doctype():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        "from frappe.model.utils.user_settings import get_user_settings, update_user_settings",
        'USER_SETTINGS_SCOPE = "VetEdge Report Center"',
        'SETTINGS_KEY = "vetedge_report_views_v1"',
        "get_saved_report_views(report_name: str)",
        "save_report_view(",
        "delete_saved_report_view(view_id: str)",
        "require_reporting_entitlement(name, \"report\"",
    ):
        assert expected in source

    assert "frappe.new_doc" not in source
    assert "insert(ignore_permissions" not in source
    assert "ignore_permissions=True" not in source


def test_saved_view_payload_is_bounded_json_safe_and_does_not_store_report_rows():
    source = SOURCE.read_text(encoding="utf-8")

    for expected in (
        "MAX_VIEWS_PER_USER = 25",
        "MAX_LABEL_LENGTH = 80",
        "MAX_FILTER_VALUE_LENGTH = 500",
        "MAX_VISIBLE_COLUMNS = 100",
        "ALLOWED_FILTER_KEYS = {",
        '"filters": filters',
        '"visible_columns": columns',
        "timestamp = now()",
    ):
        assert expected in source

    for forbidden in (
        '"rows"',
        '"result_rows"',
        '"report_data"',
        "now_datetime",
        "frappe.db.sql",
        "frappe.db.set_value",
    ):
        assert forbidden not in source


def test_saved_views_are_current_user_only_and_not_shared_yet():
    source = SOURCE.read_text(encoding="utf-8")

    assert "frappe.session.user" in source
    assert 'user == "Guest"' in source
    assert "recipient_user" not in source
    assert "shared_with" not in source
    assert "public_view" not in source.lower().replace("_public_view", "")
