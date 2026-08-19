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
        "apply_saved_report_view(view_id: str, report_name: str)",
        "save_report_view(",
        "rename_saved_report_view(view_id: str, report_name: str, label: str)",
        "delete_saved_report_view(view_id: str)",
        'require_reporting_action(name, "report", "view"',
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


def test_saved_view_list_hides_state_and_apply_revalidates_current_scope():
    source = SOURCE.read_text(encoding="utf-8")

    list_method = source.split("def get_saved_report_views", 1)[1].split("def apply_saved_report_view", 1)[0]
    apply_method = source.split("def apply_saved_report_view", 1)[1].split("def save_report_view", 1)[0]
    normalizer = source.split("def _normalize_saved_scope", 1)[1].split("@frappe.whitelist()", 1)[0]

    assert "include_state=False" in list_method
    assert '"filters"' not in list_method
    assert '"visible_columns"' not in list_method
    assert "_normalize_saved_scope" in apply_method
    assert "removed_filter_keys" in apply_method
    assert "normalize_report_filters" in normalizer
    assert "search_report_filter_options" in normalizer
    assert 'filters.pop("branch", None)' in normalizer


def test_saved_views_are_current_user_only_and_not_shared_yet():
    source = SOURCE.read_text(encoding="utf-8")

    assert "frappe.session.user" in source
    assert 'user == "Guest"' in source
    assert "recipient_user" not in source
    assert "shared_with" not in source
    assert "public_view" not in source.lower().replace("_public_view", "")
