from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_reporting_settings_patch_is_registered_and_idempotent():
	patches = (ROOT / "patches.txt").read_text()
	patch = (ROOT / "patches/add_reporting_action_settings.py").read_text()
	assert "vetedge.patches.add_reporting_action_settings" in patches
	assert '"enable_reporting_print"' in patch
	assert '"enable_reporting_export"' in patch
	assert 'frappe.db.exists("Custom Field", name)' in patch


def test_capability_policy_combines_settings_scope_and_action_permission():
	source = (ROOT / "services/reporting_capabilities.py").read_text()
	for expected in (
		"validate_report_access",
		"validate_dashboard_access",
		"enable_reporting_print",
		"enable_reporting_export",
		"frappe.has_permission(ref_doctype, ptype=action, user=user)",
		'"authorization_model": "settings_scope_and_action_permission"',
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


def test_dashboard_shell_actions_reauthorize_and_use_dashboard_payload():
	source = (ROOT / "services/dashboard_reporting_actions.py").read_text()
	for expected in (
		'@frappe.read_only()',
		'require_reporting_action(key, scope_type="dashboard", action="export")',
		'require_reporting_action(key, scope_type="dashboard", action="print")',
		'get_dashboard_payload(key, filters_dict)',
		'_set_download_response(content, filename, file_format)',
	):
		assert expected in source
	for forbidden in (
		"ignore_permissions",
		"frappe.db.set_value",
		".submit()",
		".cancel()",
	):
		assert forbidden not in source


def test_dashboard_alignment_uses_shared_dashboard_shell_with_opt_in_actions():
	source = (ROOT / "public/js/vetedge_dashboard_alignment.bundle.js").read_text()
	for expected in (
		"EdgeDashboardShell",
		'exportEnabled: Boolean(this.capabilities.can_export)',
		'printEnabled: Boolean(this.capabilities.can_print)',
		'onExport: this.handleExport',
		'onPrint: this.handlePrint',
		'window.EdgeSuiteReportExport',
		'window.EdgeSuiteReportPrint',
		'vetedge.services.dashboard_reporting_actions.download_dashboard',
		'vetedge.services.dashboard_reporting_actions.get_dashboard_print_html',
	):
		assert expected in source
	assert "ignore_permissions" not in source


def test_client_capability_bridge_reads_server_authoritative_context():
	source = (ROOT / "public/js/vetedge_reporting_capabilities.js").read_text()
	assert "vetedge.services.reporting_capabilities.get_shell_capabilities" in source
	assert "can_print" in source
	assert "can_export" in source
	assert "frappe.db" not in source
	assert "ignore_permissions" not in source
