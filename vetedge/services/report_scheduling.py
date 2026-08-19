from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, cstr, validate_email_address

from vetedge.services.portal_access import require_internal_user
from vetedge.services.report_scheduling_compatibility import NATIVE_AUTO_EMAIL, get_report_scheduling_compatibility
from vetedge.services.report_visibility import normalize_report_filters

AUTO_EMAIL_DOCTYPE = "Auto Email Report"
ALLOWED_FREQUENCIES = {"Daily", "Weekdays", "Weekly", "Monthly"}
ALLOWED_FORMATS = {"HTML", "XLSX", "CSV", "PDF"}
MAX_SCHEDULE_ROWS = 5000


def _parse_filters(value) -> dict:
	if not value:
		return {}
	parsed = value if isinstance(value, dict) else frappe.parse_json(value)
	if not isinstance(parsed, dict):
		frappe.throw(_("Scheduled report filters must be a JSON object."), frappe.ValidationError)
	return dict(parsed)


def _normalize_recipients(value: str) -> str:
	emails = []
	for token in cstr(value or "").replace(",", "\n").split():
		email = validate_email_address(token.strip(), throw=True)
		if email and email not in emails:
			emails.append(email)
	if not emails:
		frappe.throw(_("At least one recipient email address is required."), frappe.ValidationError)
	return "\n".join(emails)


def _validate_schedule_values(frequency: str, file_format: str, day_of_week: str | None) -> tuple[str, str, str]:
	frequency = cstr(frequency or "").strip().title()
	file_format = cstr(file_format or "").strip().upper()
	day_of_week = cstr(day_of_week or "").strip()
	if frequency not in ALLOWED_FREQUENCIES:
		frappe.throw(_("Unsupported scheduled report frequency."), frappe.ValidationError)
	if file_format not in ALLOWED_FORMATS:
		frappe.throw(_("Unsupported scheduled report format."), frappe.ValidationError)
	if frequency == "Weekly" and day_of_week not in {
		"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
	}:
		frappe.throw(_("Select a valid day of week for a Weekly scheduled report."), frappe.ValidationError)
	if frequency != "Weekly":
		day_of_week = ""
	return frequency, file_format, day_of_week


def _require_auto_email_create_permission() -> None:
	if not frappe.db.exists("DocType", AUTO_EMAIL_DOCTYPE):
		frappe.throw(_("Frappe Auto Email Report is not available on this site."), frappe.ValidationError)
	if not frappe.has_permission(AUTO_EMAIL_DOCTYPE, "create"):
		frappe.throw(_("You do not have permission to configure scheduled report delivery."), frappe.PermissionError)


@frappe.whitelist()
def create_native_report_schedule(
	report_name: str,
	email_to: str,
	frequency: str = "Daily",
	file_format: str = "XLSX",
	filters=None,
	day_of_week: str | None = None,
	send_if_data: int = 1,
	no_of_rows: int = 500,
) -> dict:
	"""Create only schedules proven compatible with Frappe Auto Email Report.

	EdgeSuite-provider reports intentionally fail closed here until their VetEdge
	export adapter path is implemented, so scheduled output cannot silently differ
	from the report the user configured.
	"""
	require_internal_user()
	compatibility = get_report_scheduling_compatibility(report_name)
	if not compatibility.get("can_configure"):
		frappe.throw(_("Scheduled report delivery is not available for this report or current Plan."), frappe.PermissionError)
	if compatibility.get("delivery_mode") != NATIVE_AUTO_EMAIL:
		frappe.throw(
			_("This report uses VetEdge reporting semantics and requires the VetEdge scheduled-export adapter."),
			frappe.ValidationError,
		)

	_require_auto_email_create_permission()
	frequency, file_format, day_of_week = _validate_schedule_values(frequency, file_format, day_of_week)
	recipients = _normalize_recipients(email_to)
	normalized_filters = dict(normalize_report_filters(compatibility["report_name"], _parse_filters(filters)) or {})
	row_limit = min(max(cint(no_of_rows) or 500, 1), MAX_SCHEDULE_ROWS)

	doc = frappe.get_doc(
		{
			"doctype": AUTO_EMAIL_DOCTYPE,
			"report": compatibility["report_name"],
			"user": frappe.session.user,
			"email_to": recipients,
			"frequency": frequency,
			"day_of_week": day_of_week or None,
			"format": file_format,
			"filters": json.dumps(normalized_filters, default=str, sort_keys=True),
			"enabled": 1,
			"send_if_data": cint(send_if_data),
			"no_of_rows": row_limit,
		}
	)
	doc.insert()
	return {
		"name": doc.name,
		"report_name": compatibility["report_name"],
		"delivery_mode": NATIVE_AUTO_EMAIL,
		"frequency": frequency,
		"format": file_format,
		"enabled": True,
		"no_of_rows": row_limit,
		"filters": normalized_filters,
	}
