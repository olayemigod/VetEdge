from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_reporting_settings_patch_is_registered_and_idempotent():
	patches = (ROOT / "patches.txt").read_text()
	patch = (ROOT / "patches/add_reporting_action_settings.py").read_text()
	assert "vetedge.patches.add_reporting_action_settings" in patches
	assert '"enable_reporting_print"' in patch
	assert '"enable_reporting_export"' in patch
	assert 'frappe.db.exists("Custom Field", name)' in patch


def test_capability_policy_combines_subscription_settings_scope_and_action_permission():
	source = (ROOT / "services/reporting_capabilities.py").read_text()
	for expected in (
		"validate_report_access",
		"validate_dashboard_access",
		"get_reporting_entitlement",
		"require_reporting_entitlement",
		"enable_reporting_print",
		"enable_reporting_export",
		"frappe.has_permission(ref_doctype, ptype=action, user=user)",
		'"authorization_model": "subscription_tier_then_settings_scope_and_action_permission"',
		'"report_tier"',
		'"subscription_entitled"',
		"can_print",
		"can_export",
	):
		assert expected in source
	assert "ignore_permissions" not in source


def test_reporting_catalog_has_standard_and_advanced_tiers_with_safe_default():
	source = (ROOT / "services/reporting_catalog.py").read_text()
	for expected in (
		'STANDARD_TIER = "standard"',
		'ADVANCED_TIER = "advanced"',
		'ADVANCED_REPORTS_FEATURE_KEY = "advanced_reports"',
		'"Consultation Register": {"tier": STANDARD_TIER}',
		'"Stock Expiry Status": {',
		'"Executive"' if False else '"executive": {',
		'catalog.get(str(scope_name or "").strip()) or {"tier": STANDARD_TIER}',
		'check_vetedge_feature_access(ADVANCED_REPORTS_FEATURE_KEY, user=user)',
		'is_enabled("advanced_reports")',
	):
		assert expected in source


def test_query_report_and_dashboard_data_paths_enforce_subscription_tier_server_side():
	reporting = (ROOT / "services/reporting_logic_v3.py").read_text()
	dashboard = (ROOT / "services/dashboard_host_payload.py").read_text()
	stock_page = (ROOT / "veterinary/page/stock_expiry_monitor/stock_expiry_monitor.py").read_text()
	assert 'require_reporting_entitlement(report_name, scope_type="report")' in reporting
	assert 'require_reporting_entitlement(key, scope_type="dashboard")' in dashboard
	assert 'require_reporting_entitlement("Stock Expiry Status", scope_type="report")' in stock_page


def test_stock_expiry_interactive_path_enforces_branch_normalization_and_bounded_search():
	source = (ROOT / "veterinary/page/stock_expiry_monitor/stock_expiry_monitor.py").read_text()
	for expected in (
		'normalize_report_filters("Stock Expiry Status", cleaned)',
		"FILTER_SEARCH_MAX_PAGE_LENGTH = 20",
		"frappe.get_list(",
		'page_length = min(max(cint(page_length) or FILTER_SEARCH_MAX_PAGE_LENGTH, 1), FILTER_SEARCH_MAX_PAGE_LENGTH)',
	):
		assert expected in source
	assert "limit_page_length: 500" not in source


def test_stock_expiry_current_page_export_uses_paginated_query_not_full_dataset():
	source = (ROOT / "services/stock_expiry_reporting_actions.py").read_text()
	current_page_block = source.split('if export_options["scope"] == "current_page":', 1)[1].split(
		"# All-filtered export", 1
	)[0]
	assert "get_stock_expiry_interactive_data(" in current_page_block
	assert "get_stock_expiry_rows(" not in current_page_block
	assert '_normalize_stock_expiry_filters(_json_dict(filters))' in source


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
