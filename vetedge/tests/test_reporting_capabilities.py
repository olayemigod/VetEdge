from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_reporting_settings_patch_is_registered_and_idempotent():
	patches = (ROOT / "patches.txt").read_text()
	patch = (ROOT / "patches/add_reporting_action_settings.py").read_text()
	assert "vetedge.patches.add_reporting_action_settings" in patches
	assert '"enable_reporting_print"' in patch
	assert '"enable_reporting_export"' in patch
	assert 'frappe.db.exists("Custom Field", name)' in patch


def test_capability_policy_combines_settings_with_existing_scope_access():
	source = (ROOT / "services/reporting_capabilities.py").read_text()
	for expected in (
		"validate_report_access",
		"validate_dashboard_access",
		"enable_reporting_print",
		"enable_reporting_export",
		'"authorization_model": "settings_and_scope_access"',
		"can_print",
		"can_export",
	):
		assert expected in source
	assert "ignore_permissions" not in source


def test_shell_action_endpoints_reauthorize_server_side():
	source = (ROOT / "services/reporting_actions.py").read_text()
	assert 'require_reporting_action(report_name, scope_type="report", action="export")' in source
	assert 'require_reporting_action(report_name, scope_type="report", action="print")' in source
	assert "download_report_export" in source
	assert "get_report_print_html" in source
	assert "ignore_permissions" not in source
