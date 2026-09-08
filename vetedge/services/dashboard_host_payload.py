from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cstr, flt

from vetedge.services import reporting_logic_v4 as v4
from vetedge.services import reporting_logic_v5 as v5
from vetedge.services.dashboard_aggregates import get_consultation_dashboard_aggregates
from vetedge.services.executive_financial_metrics import count_executive_unpaid_invoices
from vetedge.services.lab_order_report import get_lab_order_report_view
from vetedge.services.report_visibility import normalize_dashboard_filters, validate_dashboard_access
from vetedge.services.reporting_catalog import require_reporting_entitlement
from vetedge.services.vaccination_report import get_vaccination_report_view


@frappe.whitelist()
def get_dashboard_payload(dashboard_key: str, filters=None):
	"""Shared-dashboard adapter with aggregate-first clinical/dashboard paths."""
	key = cstr(dashboard_key or "").strip()
	require_reporting_entitlement(key, scope_type="dashboard")
	validate_dashboard_access(key)
	normalized = normalize_dashboard_filters(key, v4._to_dict(filters))

	if key == "executive":
		return _executive_payload(normalized)
	if key == "clinical":
		return _clinical_payload(normalized)
	if key == "lab":
		return _lab_payload(normalized)
	if key == "vaccination":
		return _vaccination_payload(normalized)
	if key in {"branch_performance", "practitioner_performance"}:
		payload = v5.get_dashboard_payload(key, normalized)
		return _enhance_performance_charts(key, payload)
	return v5.get_dashboard_payload(key, normalized)


def _executive_payload(filters) -> dict:
	"""Preserve Executive semantics while avoiding consultation detail-row materialization."""
	consultations = get_consultation_dashboard_aggregates(filters)
	# Financial branch/service attribution still relies on the canonical unified
	# financial dataset. Do not replace it with simplistic Sales Invoice SQL.
	revenue_rows = v4._rows("Revenue Summary", filters)
	unpaid_count = count_executive_unpaid_invoices(filters)

	payload = v5._base_payload("executive", _("Executive Dashboard"))
	payload["kpis"] = [
		v4._kpi(_("Consultations in Range"), consultations["total"]),
		v4._kpi(_("Revenue in Range"), v4._currency(sum(flt(row.get("grand_total")) for row in revenue_rows))),
		v4._kpi(_("Unpaid Invoices in Range"), unpaid_count),
		v4._kpi(_("Appointments in Range"), v5._appointments_in_range(filters)),
		v4._kpi(_("Active Patients (Current)"), v4._active_patients(filters)),
	]
	payload["charts"] = []
	if v4._is_multi_day_range(filters):
		_append_chart(payload, _series_chart(_("Consultations per Day"), "line", consultations["by_day"], _("Consultations")))
	_append_chart(payload, _series_chart(_("Consultations by Branch"), "bar", consultations["by_branch"], _("Consultations")))
	_append_chart(payload, _series_chart(_("Consultations by Type"), "bar", consultations["by_type"], _("Consultations")))
	payload["charts"].extend(
		[
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
	payload["performance_metadata"] = {
		"consultation_mode": "database_aggregate",
		"financial_mode": "canonical_financial_dataset",
	}
	return payload


def _clinical_payload(filters) -> dict:
	consultations = get_consultation_dashboard_aggregates(filters)
	lab = get_lab_order_report_view(filters=filters, start=0, page_length=1)
	vaccination = get_vaccination_report_view(filters=filters, start=0, page_length=1)
	lab_summary = _summary_map(lab)
	vaccination_summary = _summary_map(vaccination)

	payload = v5._base_payload("clinical", _("Clinical Dashboard"))
	payload["kpis"] = [
		v4._kpi(_("Consultations in Range"), consultations["total"]),
		v4._kpi(_("Lab Orders Pending"), lab_summary.get("Pending", 0)),
		v4._kpi(_("Vaccinations Due Soon"), vaccination_summary.get("Due Soon", 0)),
		v4._kpi(_("Vaccinations Overdue"), vaccination_summary.get("Overdue", 0)),
	]
	if v4._is_multi_day_range(filters):
		_append_chart(payload, _series_chart(_("Consultations per Day"), "line", consultations["by_day"], _("Consultations")))
	_append_chart(payload, lab.get("chart"))
	_append_chart(payload, vaccination.get("chart"))
	payload["performance_metadata"] = {
		"consultation_mode": "database_aggregate",
		"lab_mode": "aggregate_provider",
		"vaccination_mode": "aggregate_provider",
	}
	return payload


def _lab_payload(filters) -> dict:
	view = get_lab_order_report_view(filters=filters, start=0, page_length=1)
	summary = _summary_map(view)
	payload = v5._base_payload("lab", _("Laboratory Dashboard"))
	payload["kpis"] = [
		v4._kpi(_("Lab Orders in Range"), summary.get("Total Lab Orders", view.get("total", 0))),
		v4._kpi(_("Pending"), summary.get("Pending", 0)),
		v4._kpi(_("Completed / Reviewed"), summary.get("Completed / Reviewed", 0)),
	]
	_append_chart(payload, view.get("chart"))
	payload["performance_metadata"] = {"lab_mode": "aggregate_provider", "detail_rows_requested": 1}
	return payload


def _vaccination_payload(filters) -> dict:
	view = get_vaccination_report_view(filters=filters, start=0, page_length=1)
	summary = _summary_map(view)
	payload = v5._base_payload("vaccination", _("Vaccination Dashboard"))
	payload["kpis"] = [
		v4._kpi(_("Vaccination Records in Range"), summary.get("Vaccination Records", view.get("total", 0))),
		v4._kpi(_("Due Soon"), summary.get("Due Soon", 0)),
		v4._kpi(_("Overdue"), summary.get("Overdue", 0)),
	]
	_append_chart(payload, view.get("chart"))
	payload["performance_metadata"] = {"vaccination_mode": "aggregate_provider", "detail_rows_requested": 1}
	return payload


def _summary_map(view: dict) -> dict[str, object]:
	return {
		cstr(card.get("label")): card.get("value")
		for card in view.get("summary") or []
		if isinstance(card, dict) and card.get("label")
	}


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


def _series_chart(title: str, chart_type: str, series: list[dict], dataset_name: str) -> dict:
	labels = [cstr(item.get("label")) for item in series or [] if item.get("label") not in (None, "")]
	values = [int(flt(item.get("value"))) for item in series or [] if item.get("label") not in (None, "")]
	return {
		"title": title,
		"type": chart_type,
		"data": {"labels": labels, "datasets": [{"name": dataset_name, "values": values}]},
		"value_type": "int",
		"fieldtype": "Int",
	}


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


def _append_chart(payload: dict, chart: dict | None) -> None:
	if not chart or not chart.get("data", {}).get("labels"):
		return
	title = cstr(chart.get("title"))
	charts = payload.setdefault("charts", [])
	if any(cstr(existing.get("title")) == title for existing in charts):
		return
	charts.append(chart)
