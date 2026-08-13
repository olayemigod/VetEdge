from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cstr, flt

from vetedge.services import reporting_logic_v4 as v4
from vetedge.services import reporting_logic_v5 as v5
from vetedge.services.executive_financial_metrics import count_executive_unpaid_invoices
from vetedge.services.report_visibility import normalize_dashboard_filters, validate_dashboard_access


@frappe.whitelist()
def get_dashboard_payload(dashboard_key: str, filters=None):
	"""Shared-dashboard adapter with optimized Executive and QA chart enrichments."""
	key = cstr(dashboard_key or "").strip()
	if key != "executive":
		if key not in {"branch_performance", "practitioner_performance"}:
			return v5.get_dashboard_payload(key, filters)
		payload = v5.get_dashboard_payload(key, filters)
		return _enhance_performance_charts(key, payload)

	validate_dashboard_access(key)
	normalized = normalize_dashboard_filters(key, v4._to_dict(filters))
	return _executive_payload(normalized)


def _executive_payload(filters) -> dict:
	"""Preserve reporting_logic_v5 Executive semantics without full unpaid report rows."""
	consultation_rows = v4._rows("Consultation Register", filters)
	revenue_rows = v4._rows("Revenue Summary", filters)
	unpaid_count = count_executive_unpaid_invoices(filters)

	payload = v5._base_payload("executive", _("Executive Dashboard"))
	payload["kpis"] = [
		v4._kpi(_("Consultations in Range"), len(consultation_rows)),
		v4._kpi(_("Revenue in Range"), v4._currency(sum(flt(row.get("grand_total")) for row in revenue_rows))),
		v4._kpi(_("Unpaid Invoices in Range"), unpaid_count),
		v4._kpi(_("Appointments in Range"), v5._appointments_in_range(filters)),
		v4._kpi(_("Active Patients (Current)"), v4._active_patients(filters)),
	]
	payload["charts"] = []
	if v4._is_multi_day_range(filters):
		payload["charts"].append(v5._consultation_chart(consultation_rows))
	payload["charts"].extend(
		[
			v4._consultation_by_branch_chart(consultation_rows),
			v4._consultation_type_chart(consultation_rows),
			v4._daily_revenue_chart(revenue_rows),
			v4._branch_revenue_chart(revenue_rows),
		]
	)
	payload["filter_scope"] = {
		"from_date": filters.get("from_date"),
		"to_date": filters.get("to_date"),
		"branch": filters.get("branch"),
		"message": _("KPI cards and charts use the same selected date range. Active Patients is a current-state snapshot."),
	}
	return payload


def _enhance_performance_charts(key: str, payload: dict) -> dict:
	if key == "branch_performance":
		rows = _supporting_rows(payload)
		labels = [cstr(row.get("branch") or "").strip() for row in rows]
		values = [int(flt(row.get("consultation_count"))) for row in rows]
		_append_chart(payload, _bar_chart(_("Consultations by Branch"), labels, values))
	elif key == "practitioner_performance":
		rows = _supporting_rows(payload)
		consultations: dict[str, int] = defaultdict(int)
		vaccinations: dict[str, int] = defaultdict(int)
		for row in rows:
			practitioner = cstr(row.get("practitioner") or "").strip()
			if not practitioner:
				continue
			consultations[practitioner] += int(flt(row.get("number_of_consultations")))
			vaccinations[practitioner] += int(flt(row.get("vaccinations_administered")))
		labels = sorted(set(consultations) | set(vaccinations))
		_append_chart(
			payload,
			_bar_chart(
				_("Consultations by Practitioner"),
				labels,
				[consultations.get(label, 0) for label in labels],
			),
		)
		_append_chart(
			payload,
			_bar_chart(
				_("Vaccinations by Practitioner"),
				labels,
				[vaccinations.get(label, 0) for label in labels],
			),
		)
	return payload


def _supporting_rows(payload: dict) -> list[dict]:
	for table in payload.get("supporting_tables") or []:
		rows = table.get("rows") or []
		if rows:
			return rows
	return []


def _bar_chart(title: str, labels: list[str], values: list[int]) -> dict:
	pairs = [(label, value) for label, value in zip(labels, values) if label]
	return {
		"title": title,
		"type": "bar",
		"data": {
			"labels": [label for label, _value in pairs],
			"datasets": [{"name": title, "values": [value for _label, value in pairs]}],
		},
		"value_type": "int",
		"fieldtype": "Int",
	}


def _append_chart(payload: dict, chart: dict) -> None:
	if not chart.get("data", {}).get("labels"):
		return
	title = cstr(chart.get("title"))
	charts = payload.setdefault("charts", [])
	if any(cstr(existing.get("title")) == title for existing in charts):
		return
	charts.append(chart)
