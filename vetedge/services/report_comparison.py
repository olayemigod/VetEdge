from __future__ import annotations

from datetime import date

import frappe
from frappe import _
from frappe.utils import add_days, cstr, flt, getdate, nowdate

from vetedge.services import consultation_report
from vetedge.services.portal_access import require_internal_user
from vetedge.services.reporting_capabilities import require_reporting_action

SUPPORTED_REPORTS = {"Consultation Register"}
DEFAULT_PERIOD_DAYS = 30


def _parse_filters(value) -> dict:
	if not value:
		return {}
	parsed = value if isinstance(value, dict) else frappe.parse_json(value)
	if not isinstance(parsed, dict):
		frappe.throw(_("Expected report filters as a JSON object."), frappe.ValidationError)
	return {str(key): item for key, item in parsed.items() if item not in (None, "")}


def _period_dates(filters: dict) -> tuple[date, date, date, date]:
	current_to = getdate(filters.get("to_date") or nowdate())
	current_from = getdate(filters.get("from_date") or add_days(current_to, -(DEFAULT_PERIOD_DAYS - 1)))
	if current_from > current_to:
		frappe.throw(_("From Date cannot be after To Date."), frappe.ValidationError)
	period_days = max((current_to - current_from).days + 1, 1)
	comparison_to = getdate(add_days(current_from, -1))
	comparison_from = getdate(add_days(comparison_to, -(period_days - 1)))
	return current_from, current_to, comparison_from, comparison_to


def _period_filters(filters: dict, from_date: date, to_date: date) -> dict:
	result = dict(filters)
	result["from_date"] = cstr(from_date)
	result["to_date"] = cstr(to_date)
	result.pop("date_preset", None)
	return result


def _consultation_metrics(filters: dict) -> dict[str, float | int]:
	report_filters = consultation_report._filters(filters)
	query_filters = consultation_report._query_filters(report_filters)
	where_sql, params = consultation_report._where_clause(query_filters, report_filters)
	total = consultation_report._count_rows(where_sql, params)
	status_counts = consultation_report._status_counts(where_sql, params)
	completed = sum(status_counts.get(status, 0) for status in consultation_report.COMPLETED_STATUSES)
	cancelled = sum(status_counts.get(status, 0) for status in consultation_report.CANCELLED_STATUSES)
	planned_total = consultation_report._planned_total(where_sql, params)
	follow_up = consultation_report._follow_up_count(query_filters, report_filters, total)
	return {
		"total_consultations": total,
		"completed": completed,
		"cancelled": cancelled,
		"completion_rate": flt((completed / total) * 100, 1) if total else 0,
		"average_planned_value": flt(planned_total / total, 2) if total else 0,
		"follow_up_required": follow_up,
	}


def _delta(current: float | int, comparison: float | int) -> tuple[float, float | None]:
	change = flt(current) - flt(comparison)
	if not flt(comparison):
		return change, None
	return change, flt((change / abs(flt(comparison))) * 100, 1)


def _metric(
	key: str,
	label: str,
	current: float | int,
	comparison: float | int,
	datatype: str,
	positive_is_good: bool | None = None,
) -> dict:
	change, change_percent = _delta(current, comparison)
	tone = "neutral"
	if positive_is_good is True and change:
		tone = "positive" if change > 0 else "negative"
	elif positive_is_good is False and change:
		tone = "negative" if change > 0 else "positive"
	return {
		"key": key,
		"label": label,
		"current": current,
		"comparison": comparison,
		"delta": change,
		"delta_percent": change_percent,
		"datatype": datatype,
		"delta_tone": tone,
	}


def _consultation_comparison(filters: dict) -> dict:
	current_from, current_to, comparison_from, comparison_to = _period_dates(filters)
	current_filters = _period_filters(filters, current_from, current_to)
	comparison_filters = _period_filters(filters, comparison_from, comparison_to)
	current = _consultation_metrics(current_filters)
	previous = _consultation_metrics(comparison_filters)
	metrics = [
		_metric("total_consultations", _("Total Consultations"), current["total_consultations"], previous["total_consultations"], "Int"),
		_metric("completed", _("Completed"), current["completed"], previous["completed"], "Int", positive_is_good=True),
		_metric("completion_rate", _("Completion Rate"), current["completion_rate"], previous["completion_rate"], "Percent", positive_is_good=True),
		_metric("average_planned_value", _("Average Planned Value"), current["average_planned_value"], previous["average_planned_value"], "Currency"),
		_metric("follow_up_required", _("Follow-up Required"), current["follow_up_required"], previous["follow_up_required"], "Int"),
		_metric("cancelled", _("Cancelled"), current["cancelled"], previous["cancelled"], "Int", positive_is_good=False),
	]
	return {
		"title": _("Previous Period Comparison"),
		"current_label": _("{0} to {1}").format(current_from, current_to),
		"comparison_label": _("{0} to {1}").format(comparison_from, comparison_to),
		"metrics": metrics,
		"metadata": {
			"comparison_mode": "previous_equal_period",
			"aggregate_only": True,
			"detail_rows_materialized": False,
			"period_days": (current_to - current_from).days + 1,
		},
	}


@frappe.whitelist()
@frappe.read_only()
def get_report_comparison(report_name: str, filters=None) -> dict:
	require_internal_user()
	report_name = cstr(report_name or "").strip()
	if report_name not in SUPPORTED_REPORTS:
		frappe.throw(_("Period comparison is not available for this report yet."), frappe.ValidationError)
	require_reporting_action(report_name, "report", "view")
	parsed_filters = _parse_filters(filters)
	if report_name == "Consultation Register":
		return _consultation_comparison(parsed_filters)
	frappe.throw(_("Period comparison is not available for this report yet."), frappe.ValidationError)
