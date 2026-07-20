from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cstr, flt

from vetedge.services.financial_component_insights import get_component_financial_insights
from vetedge.services.reporting_logic_v4 import (
	_branch_revenue_chart,
	_chart,
	_daily_revenue_chart,
	_to_dict,
	_unpaid_status_chart,
)
from vetedge.services.reporting_logic_v4 import (
	get_dashboard_payload as get_v4_dashboard_payload,
)


def _income_source_chart(composition: list[dict]) -> dict:
	labels = [cstr(row.get("title")) for row in composition if row.get("title")]
	values = [flt(row.get("value")) for row in composition if row.get("title")]
	return _chart(
		_("Revenue by Income Source"),
		"bar",
		labels,
		values,
		"#6366f1",
		"currency",
	)


@frappe.whitelist()
def get_dashboard_payload(dashboard_key: str, filters=None):
	"""Return V4 dashboards with component-aware Veterinary financial metrics."""
	key = cstr(dashboard_key or "").strip()
	if key != "financial":
		payload = get_v4_dashboard_payload(dashboard_key, filters)
		if payload.get("title") == "VetEdge Dashboard":
			payload["title"] = _("Veterinary Dashboard")
		return payload

	payload = get_v4_dashboard_payload(dashboard_key, filters)
	insights = get_component_financial_insights(_to_dict(filters))
	current_dataset = insights.get("dataset") or []
	for row in current_dataset:
		row["name"] = row.get("sales_invoice")
		row["service_category"] = row.get("service_source")

	submitted_rows = [row for row in current_dataset if row.get("docstatus") == 1]
	unpaid_rows = [row for row in submitted_rows if flt(row.get("outstanding_amount")) > 0]
	composition = insights.get("revenue_composition") or []

	payload.update(
		{
			"title": _("Financial Dashboard"),
			"kpis": insights.get("kpis") or [],
			"collection_metrics": insights.get("collection_metrics") or [],
			"revenue_composition": composition,
			"outstanding_breakdowns": insights.get("outstanding_breakdowns") or {},
			"health_indicators": insights.get("health_indicators") or [],
			"alerts": insights.get("alerts") or [],
			"charts": [
				_daily_revenue_chart(submitted_rows),
				_branch_revenue_chart(submitted_rows),
				_income_source_chart(composition),
				_unpaid_status_chart(unpaid_rows),
			],
		}
	)
	return payload
