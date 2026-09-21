from __future__ import annotations

import json
import re
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
			inputDatetime: dates.formatInputDateTime('2026-09-07T14:05'),
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
		"inputDatetime": "07-09-2026 14:05",
		"alreadyFormatted": "07-09-2026",
		"unknown": "not-a-date",
		"inferredDatetime": "07-09-2026 14:05",
		"inferredDate": "07-09-2026",
	}


def test_formatter_loads_before_vetedge_pages_and_report_enhancer_uses_it():
	hooks = read(APP / "hooks.py")
	reports = read(APP / "public/js/report_visibility.js")
	assert hooks.index("vetedge_datetime.js") < hooks.index("dashboard_shell.js")
	assert "vetedge_datetime.js?v=20260921-2" in hooks
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
	assert 'frappe.db.get_single_value("System Settings", "date_format")' in setup
	assert "frappe.db.set_single_value(" in setup
	assert '"date_format",' in setup
	assert "settings.save(ignore_permissions=True)" not in setup
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
	assert "vetedge_ui_bridge.js?v=20260921-2" in hooks


def test_direct_home_and_history_dates_use_explicit_display_helpers():
	home = read(APP / "public/js/vetedge_home/VetEdgeHome.vue")
	history = read(APP / "public/js/veterinary_medical_history/VeterinaryMedicalHistory.vue")
	assert "formatDate(selectedDate || payload.context?.operational_date)" in home
	assert "formatDate(payload.context?.operational_date)" in home
	assert "formatDate(filters.from_date)" in history
	assert "formatDate(filters.to_date)" in history

def test_edgesuite_date_inputs_use_vetedge_display_wrapper():
	bridge = read(APP / "public/js/vetedge_ui_bridge.js")
	assert "installDateInputFormatting(edgeUI)" in bridge
	assert 'edgeUI.registerComponent("EdgeInput", VetEdgeInput, { replace: true })' in bridge
	assert '["date", "datetime-local"].includes(type)' in bridge
	assert "VetEdgeDateTime?.formatInputDateTime" in bridge
	assert "VetEdgeDateTime?.formatDate" in bridge
	assert 'const hint = type === "datetime-local" ? "DD-MM-YYYY HH:mm" : "DD-MM-YYYY"' in bridge
	assert "state.dateInputPatched = true" in bridge


def test_custom_desk_vue_surfaces_do_not_render_raw_native_date_inputs():
	offenders = []
	pattern = re.compile(r'<input\\b[^>]*\\btype=["\\\'](?:date|datetime-local)["\\\']', re.IGNORECASE | re.DOTALL)
	for path in (APP / "public/js").rglob("*.vue"):
		if pattern.search(read(path)):
			offenders.append(path.relative_to(APP).as_posix())
	assert offenders == []


def test_key_operational_date_fields_flow_through_edgesuite_input():
	clinical = read(APP / "public/js/vetedge_clinical_workspace/VetEdgeClinicalWorkspace.vue")
	appointments = read(APP / "public/js/vetedge_resource_center/VetEdgeAppointmentFlow.vue")
	executive = read(APP / "public/js/vetedge_executive_dashboard/VetedgeExecutiveDashboard.vue")
	service_ops = read(APP / "public/js/vetedge_service_operations/VetEdgeServiceOperations.vue")
	front_desk = read(APP / "public/js/vetedge_front_desk_action_center/VetEdgeFrontDeskActionCenter.vue")

	assert '<EdgeInput :model-value="form.consultation_datetime" type="datetime-local" label="Consultation Date/Time"' in clinical
	assert '<EdgeInput :model-value="form.follow_up_date" type="datetime-local" label="Follow-up Date/Time"' in clinical
	assert 'v-model="form.appointment_datetime"' in appointments and 'type="datetime-local"' in appointments
	assert 'v-model="filters.from_date"' in executive and '<EdgeInput' in executive
	assert 'v-model="careDialog.values.care_datetime" type="datetime-local"' in service_ops
	assert 'v-model="actionDialog.values.new_date" type="date"' in front_desk


def test_public_appointment_datetime_inputs_show_explicit_vetedge_format():
	guest = read(APP / "www/vetedge_guest_booking.html")
	owner = read(APP / "templates/includes/owner_portal_shell.html")

	for surface in (guest, owner):
		assert "DD-MM-YYYY HH:mm" in surface
		assert "VetEdgeDateTime?.formatInputDateTime" in surface
		assert 'vetedge_datetime.js?v=20260921-2' in surface

	assert 'id="vetedge-guest-preferred-datetime-display"' in guest
	assert 'id="vetedge-guest-preferred-datetime" name="preferred_datetime" type="datetime-local"' in guest
	assert 'id="vetedge-request-datetime-display"' in owner
	assert 'id="vetedge-request-datetime" type="datetime-local"' in owner

