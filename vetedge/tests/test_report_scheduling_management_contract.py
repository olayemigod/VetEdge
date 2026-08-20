from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "services/report_scheduling_management.py"
UI = ROOT / "public/js/vetedge_report_scheduling_management_ui.js"
PDF_PATCH = ROOT / "public/js/report_pdf_patch.js"


def test_management_lists_only_current_users_vetedge_catalog_schedules():
    source = SERVICE.read_text(encoding="utf-8")

    assert 'filters={"user": frappe.session.user}' in source
    assert "target not in REPORT_CATALOG" in source
    assert "page_length=100" in source
    assert '"delivery_mode": "vetedge_export_adapter" if row.get("report") == BRIDGE_REPORT else "native_auto_email"' in source


def test_management_handles_native_and_optimized_target_identity():
    source = SERVICE.read_text(encoding="utf-8")

    assert "description.startswith(DESCRIPTION_PREFIX)" in source
    assert "row.get(\"report\") == BRIDGE_REPORT" in source
    assert 'filters.get("target_report")' in source
    assert 'return canonical_report_name(row.get("report") or "")' in source


def test_management_mutations_are_owner_and_permission_checked():
    source = SERVICE.read_text(encoding="utf-8")

    assert "if doc.user != frappe.session.user:" in source
    assert 'doc.check_permission("write")' in source
    assert 'doc.check_permission("delete")' in source
    assert "ignore_permissions" not in source


def test_complete_management_ui_replaces_partial_manager_action():
    source = UI.read_text(encoding="utf-8")
    loader = PDF_PATCH.read_text(encoding="utf-8")

    assert "report_scheduling_management.get_my_report_schedules" in source
    assert "report_scheduling_management.set_report_schedule_enabled" in source
    assert "report_scheduling_management.delete_report_schedule" in source
    assert "buttons[1].style.display = \"none\"" in source
    assert 'frappe.require("/assets/vetedge/js/vetedge_report_scheduling_management_ui.js")' in loader
