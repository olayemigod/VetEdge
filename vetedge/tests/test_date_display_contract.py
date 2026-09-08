from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
FORMATTER = APP / "public/js/vetedge_datetime.js"


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_shared_date_formatter_outputs_vetedge_display_contract():
	node = shutil.which("node")
	if not node:
		return
	program = f"""
		const dates = require({json.dumps(str(FORMATTER))});
		process.stdout.write(JSON.stringify({{
			date: dates.formatDate('2026-09-07'),
			datetime: dates.formatDateTime('2026-09-07 14:05:59'),
			alreadyFormatted: dates.formatDate('07-09-2026'),
			unknown: dates.formatDate('not-a-date'),
			inferredDatetime: dates.formatCell('2026-09-07 14:05:59', {{ key: 'consultation_datetime' }}),
			inferredDate: dates.formatCell('2026-09-07', {{ fieldname: 'expiry_date' }})
		}}));
	"""
	result = subprocess.run([node, "-e", program], capture_output=True, text=True, check=False)
	assert result.returncode == 0, result.stderr
	assert json.loads(result.stdout) == {
		"date": "07-09-2026",
		"datetime": "07-09-2026 14:05",
		"alreadyFormatted": "07-09-2026",
		"unknown": "not-a-date",
		"inferredDatetime": "07-09-2026 14:05",
		"inferredDate": "07-09-2026",
	}


def test_formatter_loads_before_vetedge_pages_and_report_enhancer_uses_it():
	hooks = read(APP / "hooks.py")
	reports = read(APP / "public/js/report_visibility.js")
	assert hooks.index("vetedge_datetime.js") < hooks.index("dashboard_shell.js")
	assert "vetedge_datetime.js?v=20260908-1" in hooks
	assert hooks.index("vetedge_datetime.js") < hooks.index("billing_modal.js")
	assert "VetEdgeDateTime?.reportFormatter" in reports
	assert "report_settings.formatter = formatter" in reports


def test_custom_display_surfaces_do_not_use_site_dependent_str_to_user():
	paths = [APP / "public/js", APP / "veterinary/page"]
	offenders = []
	for root in paths:
		for suffix in ("*.js", "*.vue"):
			for path in root.rglob(suffix):
				if "/lib/" in path.as_posix():
					continue
				if "str_to_user" in read(path):
					offenders.append(path.relative_to(APP).as_posix())
	assert offenders == []


def test_report_and_dashboard_exports_format_dates_for_display():
	report_export = read(APP / "services/report_export.py")
	dashboard_export = read(APP / "services/dashboard_reporting_actions.py")
	assert 'strftime("%d-%m-%Y")' in report_export
	assert 'strftime("%d-%m-%Y %H:%M")' in report_export
	assert '_display_value(row.get(column["fieldname"]), column.get("fieldtype"))' in report_export
	assert "_display_filter_value" in dashboard_export
	assert "_display_value(frappe.utils.now_datetime(), \"Datetime\")" in dashboard_export


def test_owner_portal_uses_explicit_display_date_helpers():
	controller = read(APP / "www/vetedge_portal.py")
	template = read(APP / "templates/includes/owner_portal_shell.html")
	assert 'strftime("%d-%m-%Y")' in controller
	assert 'strftime("%d-%m-%Y %H:%M")' in controller
	assert "vetedge_datetime(appointment.appointment_datetime)" in template
	assert "vetedge_date(invoice.posting_date)" in template


def test_native_frappe_date_controls_receive_the_same_display_format():
	setup = read(APP / "setup/display_settings.py")
	patches = read(APP / "patches.txt")
	install = read(APP / "install/__init__.py")
	assert 'VETEDGE_DATE_FORMAT = "dd-mm-yyyy"' in setup
	assert 'frappe.get_single("System Settings")' in setup
	assert "settings.save(ignore_permissions=True)" in setup
	assert "vetedge.patches.set_vetedge_date_format" in patches
	assert "ensure_vetedge_date_format()" in install


def test_edgesuite_tables_apply_vetedge_date_format_before_rendering():
	bridge = read(APP / "public/js/vetedge_ui_bridge.js")
	hooks = read(APP / "hooks.py")
	assert 'installDataTableFormatting(edgeUI)' in bridge
	assert 'edgeUI.registerComponent("EdgeDataTable", VetEdgeDataTable, { replace: true })' in bridge
	assert 'window.VetEdgeDateTime?.formatCell?.(value, column)' in bridge
	assert 'formatter(value, column, row)' in bridge
	assert 'this.$emit("row-click", this.sourceRow(row))' in bridge
	assert "vetedge_ui_bridge.js?v=20260908-1" in hooks


def test_direct_home_and_history_dates_use_explicit_display_helpers():
	home = read(APP / "public/js/vetedge_home/VetEdgeHome.vue")
	history = read(APP / "public/js/veterinary_medical_history/VeterinaryMedicalHistory.vue")
	assert "formatDate(selectedDate || payload.context?.operational_date)" in home
	assert "formatDate(payload.context?.operational_date)" in home
	assert "formatDate(filters.from_date)" in history
	assert "formatDate(filters.to_date)" in history
