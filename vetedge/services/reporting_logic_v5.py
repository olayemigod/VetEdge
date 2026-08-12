from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cstr, flt, getdate

from vetedge.services import reporting_logic_v4 as v4
from vetedge.services.report_visibility import normalize_dashboard_filters, validate_dashboard_access
from vetedge.services.service_revenue import build_service_revenue_rows, summarize_service_revenue


@frappe.whitelist()
def get_dashboard_payload(dashboard_key: str, filters=None):
	"""QA-safe dashboard adapter over v4.

	This layer keeps v4 as the performance/reporting foundation while normalising
	browser-facing filter semantics and adding line-level service revenue/table data.
	"""
	key = cstr(dashboard_key or "").strip()
	validate_dashboard_access(key)
	normalized = normalize_dashboard_filters(key, v4._to_dict(filters))

	if key == "executive":
		return _executive_payload(normalized)
	if key == "clinical":
		return _clinical_payload(normalized)

	payload = v4.get_dashboard_payload(key, normalized)
	if key == "financial":
		return _financial_payload(payload, normalized)
	if key == "branch_performance":
		return _branch_performance_payload(payload, normalized)
	if key == "practitioner_performance":
		return _practitioner_performance_payload(payload, normalized)
	return payload


def _base_payload(key: str, title: str) -> dict:
	return {
		"title": title,
		"dashboard_key": key,
		"generated_on": frappe.utils.nowdate(),
		"kpis": [],
		"charts": [],
		"report_links": v4._dashboard_report_links(key),
		"notes": [],
		"supporting_tables": [],
	}


def _executive_payload(filters) -> dict:
	consultation_rows = v4._rows("Consultation Register", filters)
	revenue_rows = v4._rows("Revenue Summary", filters)
	unpaid_rows = v4._rows("Unpaid Invoice Report", filters)
	payload = _base_payload("executive", _("Executive Dashboard"))
	payload["kpis"] = [
		v4._kpi(_("Consultations in Range"), len(consultation_rows)),
		v4._kpi(_("Revenue in Range"), v4._currency(sum(flt(row.get("grand_total")) for row in revenue_rows))),
		v4._kpi(_("Unpaid Invoices in Range"), len(unpaid_rows)),
		v4._kpi(_("Appointments in Range"), _appointments_in_range(filters)),
		v4._kpi(_("Active Patients (Current)"), v4._active_patients(filters)),
	]
	payload["charts"] = []
	if v4._is_multi_day_range(filters):
		payload["charts"].append(_consultation_chart(consultation_rows))
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


def _clinical_payload(filters) -> dict:
	consultation_rows = v4._rows("Consultation Register", filters)
	lab_rows = v4._rows("Lab Order Report", filters)
	vaccination_rows = v4._rows("Vaccination Report", filters)
	due_soon = sum(1 for row in vaccination_rows if cstr(row.get("due_status")) == "Due Soon")
	overdue = sum(1 for row in vaccination_rows if cstr(row.get("due_status")) == "Overdue")
	payload = _base_payload("clinical", _("Clinical Dashboard"))
	payload["kpis"] = [
		v4._kpi(_("Consultations in Range"), len(consultation_rows)),
		v4._kpi(
			_("Lab Orders Pending"),
			sum(1 for row in lab_rows if cstr(row.get("status")) in {"Pending", "Open", "Requested"}),
		),
		v4._kpi(_("Vaccinations Due Soon"), due_soon),
		v4._kpi(_("Vaccinations Overdue"), overdue),
	]
	payload["charts"] = []
	if v4._is_multi_day_range(filters):
		payload["charts"].append(_consultation_chart(consultation_rows))
	payload["charts"].extend([v4._lab_status_chart(lab_rows), v4._vaccination_due_chart(vaccination_rows)])
	return payload


def _consultation_chart(rows: list[dict]) -> dict:
	grouped: dict[str, int] = defaultdict(int)
	for row in rows:
		value = row.get("consultation_datetime") or row.get("consultation_date")
		if not value:
			continue
		grouped[cstr(getdate(value))] += 1
	labels = sorted(grouped)
	return v4._chart(_("Consultations per Day"), "line", labels, [grouped[label] for label in labels], "#5b8def")


def _appointments_in_range(filters) -> int:
	doctype = "Veterinary Appointment"
	if not frappe.db.exists("DocType", doctype):
		return 0
	meta = frappe.get_meta(doctype)
	date_field = "appointment_datetime" if meta.get_field("appointment_datetime") else (
		"appointment_date" if meta.get_field("appointment_date") else None
	)
	branch_field = "service_branch" if meta.get_field("service_branch") else (
		"branch" if meta.get_field("branch") else None
	)
	if not date_field:
		return 0
	from_date = cstr(filters.get("from_date") or "").strip()
	to_date = cstr(filters.get("to_date") or "").strip()
	query_filters = {}
	if from_date and to_date:
		field = meta.get_field(date_field)
		if cstr(getattr(field, "fieldtype", "")) == "Datetime":
			query_filters[date_field] = ("between", [f"{from_date} 00:00:00", f"{to_date} 23:59:59"])
		else:
			query_filters[date_field] = ("between", [from_date, to_date])
	elif from_date:
		query_filters[date_field] = (">=", from_date)
	elif to_date:
		query_filters[date_field] = ("<=", to_date)
	if filters.get("branch") and branch_field:
		query_filters[branch_field] = filters.get("branch")
	return frappe.db.count(doctype, query_filters)


def _financial_payload(payload: dict, filters) -> dict:
	service_rows = build_service_revenue_rows(filters)
	composition = summarize_service_revenue(service_rows)
	total = sum(flt(row.get("revenue_amount")) for row in composition)
	payload["revenue_composition"] = [
		{
			"id": f"service_{index}",
			"title": row.get("service_category"),
			"label": row.get("service_category"),
			"value": flt(row.get("revenue_amount")),
			"value_type": "currency",
			"share_percent": round((flt(row.get("revenue_amount")) / total * 100.0) if total else 0.0, 1),
			"secondary_value": _("{0}% of Revenue").format(
				round((flt(row.get("revenue_amount")) / total * 100.0) if total else 0.0, 1)
			),
		}
		for index, row in enumerate(composition)
	]
	_normalize_financial_health(payload, composition, total)
	payload["charts"] = [
		chart for chart in payload.get("charts", []) if cstr(chart.get("title")) != _("Revenue by Service Area")
	]
	payload["report_links"] = _append_report(payload.get("report_links"), "Service Revenue Breakdown")
	payload["service_revenue_reconciles_to"] = total
	return payload


def _normalize_financial_health(payload: dict, composition: list[dict], total: float) -> None:
	"""Keep health cards compact and keep concentration aligned to service-line analytics."""
	for card in payload.get("health_indicators") or []:
		card_id = cstr(card.get("id") or "")
		if card_id in {"billing_completion_rate", "payment_completion_rate"}:
			card["value"] = f"{round(flt(card.get('value')), 1)}%"
			card.pop("value_type", None)
			card.pop("fieldtype", None)

	if not composition or not total:
		return
	top_service = max(composition, key=lambda row: flt(row.get("revenue_amount")), default=None)
	if not top_service:
		return
	service_name = cstr(top_service.get("service_category") or _("Unassigned"))
	service_pct = round((flt(top_service.get("revenue_amount")) / total) * 100.0, 1)
	for card in payload.get("health_indicators") or []:
		if cstr(card.get("id")) != "revenue_concentration":
			continue
		secondary = cstr(card.get("secondary_value") or "")
		customer_marker = " / Customer:"
		if customer_marker in secondary:
			customer = secondary.split(customer_marker, 1)[1]
			card["secondary_value"] = f"Service: {service_name} ({service_pct}%) / Customer:{customer}"
		else:
			card["secondary_value"] = f"Service: {service_name} ({service_pct}%)"
		break


def _branch_performance_payload(payload: dict, filters) -> dict:
	branch_rows = [
		row
		for row in v4._rows("Branch Performance Report", filters)
		if cstr(row.get("branch") or "").strip() and cstr(row.get("branch")) != "Unassigned"
	]
	service_rows = build_service_revenue_rows(filters)
	service_totals = _group_service_rows(service_rows, "branch")
	rows = []
	for row in branch_rows:
		branch = cstr(row.get("branch"))
		service = service_totals.get(branch, {})
		rows.append(
			{
				**row,
				"consultation_service_revenue": flt(service.get("Consultation Service")),
				"treatment_revenue": flt(service.get("Treatment")),
			}
		)
	payload["supporting_tables"] = [
		{
			"title": _("Branch Performance Detail"),
			"description": _("Basic branch operating and revenue insights for the selected range."),
			"row_key": "branch",
			"columns": [
				_col("branch", _("Branch")),
				_col("consultation_count", _("Consultations"), "Int"),
				_col("appointment_count", _("Appointments"), "Int"),
				_col("revenue_total", _("Revenue"), "Currency"),
				_col("outstanding_total", _("Outstanding"), "Currency"),
				_col("consultation_service_revenue", _("Consultation Service"), "Currency"),
				_col("treatment_revenue", _("Treatment"), "Currency"),
				_col("lab_order_count", _("Lab Orders"), "Int"),
				_col("vaccination_count", _("Vaccinations"), "Int"),
				_col("grooming_sessions", _("Grooming"), "Int"),
				_col("active_boarding_stays", _("Active Boarding"), "Int"),
			],
			"rows": rows,
		}
	]
	payload["report_links"] = _append_report(payload.get("report_links"), "Service Revenue Breakdown")
	return payload


def _practitioner_performance_payload(payload: dict, filters) -> dict:
	practitioner_rows = v4._rows("Practitioner Performance Report", filters)
	service_rows = build_service_revenue_rows(filters)
	service_totals = _group_service_rows(service_rows, "practitioner", secondary_field="branch")
	rows = []
	for row in practitioner_rows:
		practitioner = cstr(row.get("practitioner") or "").strip()
		branch = cstr(row.get("branch") or "").strip()
		service = service_totals.get((practitioner, branch), service_totals.get((practitioner, ""), {}))
		rows.append(
			{
				**row,
				"consultation_service_revenue": flt(service.get("Consultation Service")),
				"treatment_revenue": flt(service.get("Treatment")),
			}
		)
	payload["supporting_tables"] = [
		{
			"title": _("Practitioner Performance Detail"),
			"description": _("Clinical activity and separated consultation/treatment revenue for the selected range."),
			"row_key": "practitioner",
			"columns": [
				_col("practitioner", _("Practitioner")),
				_col("branch", _("Branch")),
				_col("number_of_consultations", _("Consultations"), "Int"),
				_col("completed_consultations", _("Completed"), "Int"),
				_col("consultation_service_revenue", _("Consultation Service"), "Currency"),
				_col("treatment_revenue", _("Treatment"), "Currency"),
				_col("lab_orders_requested", _("Lab Orders"), "Int"),
				_col("vaccinations_administered", _("Vaccinations"), "Int"),
				_col("follow_up_appointments_created", _("Follow-ups"), "Int"),
			],
			"rows": rows,
		}
	]
	payload["report_links"] = _append_report(payload.get("report_links"), "Service Revenue Breakdown")
	return payload


def _group_service_rows(rows: list[dict], field: str, secondary_field: str | None = None) -> dict:
	grouped: dict = defaultdict(lambda: defaultdict(float))
	for row in rows:
		primary = cstr(row.get(field) or "").strip()
		if not primary:
			continue
		key = (primary, cstr(row.get(secondary_field) or "").strip()) if secondary_field else primary
		grouped[key][cstr(row.get("service_category"))] += flt(row.get("revenue_amount"))
	return grouped


def _append_report(links, report_name: str) -> list[dict]:
	links = list(links or [])
	if not any(cstr(link.get("report")) == report_name for link in links):
		links.append({"label": report_name, "report": report_name})
	return links


def _col(fieldname: str, label: str, fieldtype: str = "Data") -> dict:
	return {"fieldname": fieldname, "label": label, "fieldtype": fieldtype}
