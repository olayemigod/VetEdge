from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, cstr, validate_email_address

from vetedge.services.portal_access import require_internal_user
from vetedge.services.report_scheduling_compatibility import (
	NATIVE_AUTO_EMAIL,
	VETEDGE_EXPORT_ADAPTER,
	get_report_scheduling_compatibility,
)
from vetedge.services.report_visibility import normalize_report_filters

AUTO_EMAIL_DOCTYPE = "Auto Email Report"
BRIDGE_REPORT = "VetEdge Scheduled Report Bridge"
DESCRIPTION_PREFIX = "Scheduled VetEdge report: "
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


def _parse_columns(value) -> list[str]:
	if not value:
		return []
	parsed = value if isinstance(value, list) else frappe.parse_json(value)
	if not isinstance(parsed, list):
		frappe.throw(_("Scheduled report columns must be a JSON list."), frappe.ValidationError)
	return [cstr(item).strip() for item in parsed if cstr(item).strip()]


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


def _schedule_doc(
	*,
	report: str,
	recipients: str,
	frequency: str,
	file_format: str,
	filters: dict,
	day_of_week: str,
	send_if_data: int,
	row_limit: int,
	description: str,
):
	doc = frappe.get_doc(
		{
			"doctype": AUTO_EMAIL_DOCTYPE,
			"report": report,
			"user": frappe.session.user,
			"email_to": recipients,
			"frequency": frequency,
			"day_of_week": day_of_week or None,
			"format": file_format,
			"filters": json.dumps(filters, default=str, sort_keys=True),
			"enabled": 1,
			"send_if_data": cint(send_if_data),
			"no_of_rows": row_limit,
			"description": description,
		}
	)
	doc.insert()
	return doc


def _owned_vetedge_schedule(name: str):
	doc = frappe.get_doc(AUTO_EMAIL_DOCTYPE, name)
	doc.check_permission("read")
	if doc.user != frappe.session.user or not cstr(doc.description or "").startswith(DESCRIPTION_PREFIX):
		frappe.throw(_("You are not permitted to manage this scheduled report."), frappe.PermissionError)
	return doc


def _target_from_schedule(row: dict) -> str:
	description = cstr(row.get("description") or "")
	if description.startswith(DESCRIPTION_PREFIX):
		return description[len(DESCRIPTION_PREFIX):].strip()
	return ""


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
	"""Create only schedules proven compatible with Frappe Auto Email Report."""
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

	doc = _schedule_doc(
		report=compatibility["report_name"],
		recipients=recipients,
		frequency=frequency,
		file_format=file_format,
		filters=normalized_filters,
		day_of_week=day_of_week,
		send_if_data=send_if_data,
		row_limit=row_limit,
		description=f"{DESCRIPTION_PREFIX}{compatibility['report_name']}",
	)
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


@frappe.whitelist()
def create_vetedge_report_schedule(
	report_name: str,
	email_to: str,
	frequency: str = "Daily",
	file_format: str = "XLSX",
	filters=None,
	selected_columns=None,
	day_of_week: str | None = None,
	send_if_data: int = 1,
	no_of_rows: int = 500,
) -> dict:
	"""Schedule optimized EdgeSuite/VetEdge report data through Frappe Auto Email Report."""
	require_internal_user()
	compatibility = get_report_scheduling_compatibility(report_name)
	if not compatibility.get("can_configure"):
		frappe.throw(_("Scheduled report delivery is not available for this report or current Plan."), frappe.PermissionError)
	if compatibility.get("delivery_mode") != VETEDGE_EXPORT_ADAPTER:
		frappe.throw(_("This report does not require the VetEdge scheduled-report adapter."), frappe.ValidationError)

	_require_auto_email_create_permission()
	if not frappe.db.exists("Report", BRIDGE_REPORT):
		frappe.throw(_("VetEdge Scheduled Report Bridge is not installed on this site."), frappe.ValidationError)

	frequency, file_format, day_of_week = _validate_schedule_values(frequency, file_format, day_of_week)
	recipients = _normalize_recipients(email_to)
	normalized_filters = dict(normalize_report_filters(compatibility["report_name"], _parse_filters(filters)) or {})
	columns = _parse_columns(selected_columns)
	row_limit = min(max(cint(no_of_rows) or 500, 1), MAX_SCHEDULE_ROWS)
	bridge_filters = {
		"target_report": compatibility["report_name"],
		"target_filters": json.dumps(normalized_filters, default=str, sort_keys=True),
		"selected_columns": json.dumps(columns),
		"row_limit": row_limit,
	}

	doc = _schedule_doc(
		report=BRIDGE_REPORT,
		recipients=recipients,
		frequency=frequency,
		file_format=file_format,
		filters=bridge_filters,
		day_of_week=day_of_week,
		send_if_data=send_if_data,
		row_limit=row_limit,
		description=f"{DESCRIPTION_PREFIX}{compatibility['report_name']}",
	)
	return {
		"name": doc.name,
		"report_name": compatibility["report_name"],
		"delivery_mode": VETEDGE_EXPORT_ADAPTER,
		"scheduler": AUTO_EMAIL_DOCTYPE,
		"bridge_report": BRIDGE_REPORT,
		"frequency": frequency,
		"format": file_format,
		"enabled": True,
		"no_of_rows": row_limit,
		"filters": normalized_filters,
		"selected_columns": columns,
	}


@frappe.whitelist()
@frappe.read_only()
def get_my_report_schedules(report_name: str | None = None) -> list[dict]:
	require_internal_user()
	filters = {"user": frappe.session.user, "description": ["like", f"{DESCRIPTION_PREFIX}%"]}
	rows = frappe.get_list(
		AUTO_EMAIL_DOCTYPE,
		filters=filters,
		fields=["name", "report", "description", "email_to", "frequency", "day_of_week", "format", "enabled", "send_if_data", "no_of_rows", "modified"],
		order_by="modified desc",
		page_length=100,
	)
	items = []
	requested = cstr(report_name or "").strip()
	for row in rows:
		target = _target_from_schedule(row)
		if requested and target != requested:
			continue
		items.append(
			{
				"name": row.get("name"),
				"report_name": target,
				"scheduler_report": row.get("report"),
				"email_to": row.get("email_to"),
				"frequency": row.get("frequency"),
				"day_of_week": row.get("day_of_week"),
				"format": row.get("format"),
				"enabled": bool(cint(row.get("enabled"))),
				"send_if_data": bool(cint(row.get("send_if_data"))),
				"no_of_rows": cint(row.get("no_of_rows")),
				"modified": row.get("modified"),
			}
		)
	return items


@frappe.whitelist()
def set_report_schedule_enabled(name: str, enabled: int) -> dict:
	require_internal_user()
	doc = _owned_vetedge_schedule(name)
	doc.check_permission("write")
	doc.enabled = cint(enabled)
	doc.save()
	return {"name": doc.name, "enabled": bool(cint(doc.enabled))}


@frappe.whitelist()
def delete_report_schedule(name: str) -> dict:
	require_internal_user()
	doc = _owned_vetedge_schedule(name)
	doc.check_permission("delete")
	doc.delete()
	return {"name": name, "deleted": True}
