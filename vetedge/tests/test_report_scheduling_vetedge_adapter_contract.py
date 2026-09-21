from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEDULING = ROOT / "services/report_scheduling.py"
BRIDGE = ROOT / "services/scheduled_report_bridge.py"
BRIDGE_REPORT = (
    ROOT
    / "veterinary/report/vetedge_scheduled_report_bridge/vetedge_scheduled_report_bridge.py"
)
BRIDGE_JSON = (
    ROOT
    / "veterinary/report/vetedge_scheduled_report_bridge/vetedge_scheduled_report_bridge.json"
)


def test_optimized_schedule_reuses_frappe_auto_email_report_not_custom_scheduler():
    source = SCHEDULING.read_text(encoding="utf-8")

    for expected in (
        'BRIDGE_REPORT = "VetEdge Scheduled Report Bridge"',
        "def create_vetedge_report_schedule(",
        'compatibility.get("delivery_mode") != VETEDGE_EXPORT_ADAPTER',
        'report=BRIDGE_REPORT',
        '"scheduler": AUTO_EMAIL_DOCTYPE',
        '"bridge_report": BRIDGE_REPORT',
        "doc.insert()",
    ):
        assert expected in source

    for forbidden in (
        "scheduler_events",
        "frappe.enqueue(",
        "frappe.sendmail(",
        "ignore_permissions=True",
        "frappe.set_user(",
    ):
        assert forbidden not in source


def test_bridge_revalidates_target_entitlement_and_branch_scope_at_execution_time():
    source = BRIDGE.read_text(encoding="utf-8")

    for expected in (
        "get_report_scheduling_compatibility(report_name)",
        'compatibility.get("delivery_mode") != VETEDGE_EXPORT_ADAPTER',
        "normalize_report_filters(report_name",
        "MAX_BRIDGE_ROWS = 5000",
        "PAGE_LENGTH = 100",
    ):
        assert expected in source

    assert "ignore_permissions" not in source
    assert "frappe.set_user(" not in source


def test_bridge_uses_the_seven_optimized_provider_truths_and_pages_server_side():
    source = BRIDGE.read_text(encoding="utf-8")

    for expected in (
        '"Consultation Register": "vetedge.services.consultation_report.get_consultation_register_view"',
        '"Planned Treatment": "vetedge.services.treatment_plan_report.get_planned_treatment_view"',
        '"Lab Order Report": "vetedge.services.lab_order_report.get_lab_order_report_view"',
        '"Vaccination Report": "vetedge.services.vaccination_report.get_vaccination_report_view"',
        '"Patient Register": "vetedge.services.patient_report.get_patient_register_view"',
        '"Owner Register": "vetedge.services.owner_report.get_owner_register_view"',
        'STOCK_EXPIRY_REPORT = "Stock Expiry Status"',
        "while len(rows) < row_limit:",
        "page_length = min(PAGE_LENGTH, row_limit - len(rows))",
    ):
        assert expected in source


def test_selected_columns_are_allowlisted_against_provider_columns():
    source = BRIDGE.read_text(encoding="utf-8")

    assert "def _selected_columns(" in source
    assert "allowed = set(requested)" in source
    assert "None of the selected scheduled-report columns are available." in source
    assert "allowed_keys =" in source
    assert "if key in allowed_keys" in source


def test_internal_bridge_report_only_passes_encoded_target_configuration_to_service():
    source = BRIDGE_REPORT.read_text(encoding="utf-8")
    definition = BRIDGE_JSON.read_text(encoding="utf-8")

    for expected in (
        "get_scheduled_report_data",
        'report_name=filters.get("target_report")',
        'filters=filters.get("target_filters")',
        'selected_columns=filters.get("selected_columns")',
        'row_limit=filters.get("row_limit") or 500',
    ):
        assert expected in source

    assert '"name": "VetEdge Scheduled Report Bridge"' in definition
    assert '"report_type": "Script Report"' in definition
    assert '"prepared_report": 0' in definition
