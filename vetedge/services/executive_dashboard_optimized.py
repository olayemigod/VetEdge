from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cstr, flt, getdate, nowdate

from vetedge.services.executive_financial_metrics import count_executive_unpaid_invoices
from vetedge.services.reporting_logic_v3 import execute_structured_report
from vetedge.services.reporting_logic_v4 import (
	_active_patients,
	_appointments_today,
	_branch_revenue_chart,
	_consultation_by_branch_chart,
	_consultation_chart,
	_consultation_type_chart,
	_currency,
	_daily_revenue_chart,
	_dashboard_report_links,
	_is_multi_day_range,
	_kpi,
	_to_dict,
)
from vetedge.services.report_visibility import normalize_dashboard_filters, validate_dashboard_access


def get_dashboard_payload(dashboard_key: str, filters=None) -> dict:
	"""Compatibility wrapper for the established Executive payload contract."""
	key = cstr(dashboard_key or "").strip()
	if key != "executive":
		frappe.throw(_("This optimized payload builder supports only the Executive Dashboard."), frappe.ValidationError)
	return get_optimized_executive_dashboard_payload(filters)


def get_optimized_executive_dashboard_payload(filters=None) -> dict:
	"""Build the Executive Dashboard while reusing identical report datasets."""
	filters = _to_dict(filters)
	validate_dashboard_access("executive")
	filters = normalize_dashboard_filters("executive", filters)

	today = cstr(nowdate())
	month_start = cstr(getdate(today).replace(day=1))

	month_filters = frappe._dict(filters.copy())
	month_filters.from_date = cstr(filters.get("from_date") or month_start)
	month_filters.to_date = cstr(filters.get("to_date") or today)

	today_filters = frappe._dict(filters.copy())
	today_filters.from_date = today
	today_filters.to_date = today

	today_consultations = _rows("Consultation Register", today_filters)
	today_revenue = _rows("Revenue Summary", today_filters)
	unpaid_count = count_executive_unpaid_invoices(filters)

	same_range = (
		cstr(month_filters.from_date) == cstr(today_filters.from_date)
		and cstr(month_filters.to_date) == cstr(today_filters.to_date)
	)
	month_consultations = (
		today_consultations if same_range else _rows("Consultation Register", month_filters)
	)
	month_revenue = today_revenue if same_range else _rows("Revenue Summary", month_filters)

	payload = {
		"title": _("Executive Dashboard"),
		"dashboard_key": "executive",
		"generated_on": today,
		"kpis": [
			_kpi(_("Today's Consultations"), len(today_consultations)),
			_kpi(
				_("Today's Revenue"),
				_currency(sum(flt(row.get("grand_total")) for row in today_revenue)),
			),
			_kpi(_("Unpaid Invoices"), unpaid_count),
			_kpi(_("Appointments Today"), _appointments_today(filters)),
			_kpi(_("Active Patients"), _active_patients(filters)),
		],
		"charts": [],
		"report_links": _dashboard_report_links("executive"),
		"notes": [],
	}

	if _is_multi_day_range(month_filters):
		payload["charts"].append(_consultation_chart(month_consultations))
	payload["charts"].extend(
		[
			_consultation_by_branch_chart(month_consultations),
			_consultation_type_chart(month_consultations),
			_daily_revenue_chart(month_revenue),
			_branch_revenue_chart(month_revenue),
		]
	)
	return payload


def _rows(report_name: str, filters) -> list[dict]:
	return execute_structured_report(report_name, filters)[1]
