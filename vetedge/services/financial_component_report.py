from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cstr, flt

from vetedge.services.financial_component_insights import (
	CONSULTATION_SERVICE_INCOME,
	TREATMENT_INCOME,
)
from vetedge.services.financial_dataset import build_financial_dataset


INCOME_CATEGORY_OPTIONS = (
	CONSULTATION_SERVICE_INCOME,
	TREATMENT_INCOME,
	"Laboratory Income",
	"Vaccination Income",
	"Boarding Income",
	"Grooming Income",
	"Dispensary Income",
	"Registration Income",
	"General Income",
	"Other Income",
)


def _filters(value=None) -> frappe._dict:
	if not value:
		return frappe._dict()
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except (TypeError, ValueError):
			value = {}
	return frappe._dict(value or {})


def _columns() -> list[dict]:
	return [
		{"label": _("Invoice"), "fieldname": "invoice", "fieldtype": "Link", "options": "Sales Invoice", "width": 150},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 180},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 140},
		{"label": _("Income Sources"), "fieldname": "service_category", "fieldtype": "Data", "width": 220},
		{"label": _("Consultation Service Income"), "fieldname": "consultation_service_income", "fieldtype": "Currency", "width": 165},
		{"label": _("Treatment Income"), "fieldname": "treatment_income", "fieldtype": "Currency", "width": 130},
		{"label": _("Laboratory Income"), "fieldname": "laboratory_income", "fieldtype": "Currency", "width": 130},
		{"label": _("Vaccination Income"), "fieldname": "vaccination_income", "fieldtype": "Currency", "width": 135},
		{"label": _("Other Income"), "fieldname": "other_income", "fieldtype": "Currency", "width": 120},
		{"label": _("Total Revenue"), "fieldname": "grand_total", "fieldtype": "Currency", "width": 130},
		{"label": _("Paid Amount"), "fieldname": "paid_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Outstanding"), "fieldname": "outstanding_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
	]


def _row_matches_filters(row: dict, filters: frappe._dict) -> bool:
	income_category = cstr(filters.get("income_category") or "").strip()
	if income_category and income_category not in (row.get("revenue_component_labels") or []):
		return False
	legacy_category = cstr(filters.get("service_category") or "").strip()
	if legacy_category and cstr(row.get("service_source")) != legacy_category:
		return False
	return True


def _data(filters: frappe._dict) -> list[dict]:
	rows = []
	for row in build_financial_dataset(filters):
		# Revenue remains based on submitted Sales Invoices only.
		if int(row.get("docstatus") or 0) != 1 or not _row_matches_filters(row, filters):
			continue
		labels = row.get("revenue_component_labels") or []
		rows.append(
			{
				"invoice": row.get("sales_invoice"),
				"posting_date": row.get("posting_date"),
				"customer": row.get("customer"),
				"branch": row.get("branch"),
				"service_category": ", ".join(labels) or row.get("service_source") or _("General Income"),
				"consultation_service_income": flt(row.get("consultation_service_income")),
				"treatment_income": flt(row.get("treatment_income")),
				"laboratory_income": flt(row.get("laboratory_income")),
				"vaccination_income": flt(row.get("vaccination_income")),
				"other_income": flt(row.get("other_income")),
				"grand_total": flt(row.get("grand_total")),
				"paid_amount": flt(row.get("paid_amount")),
				"outstanding_amount": flt(row.get("outstanding_amount")),
				"status": row.get("payment_status"),
			}
		)
	return rows


def _component_totals(data: list[dict]) -> dict[str, float]:
	return {
		CONSULTATION_SERVICE_INCOME: sum(flt(row.get("consultation_service_income")) for row in data),
		TREATMENT_INCOME: sum(flt(row.get("treatment_income")) for row in data),
		"Laboratory Income": sum(flt(row.get("laboratory_income")) for row in data),
		"Vaccination Income": sum(flt(row.get("vaccination_income")) for row in data),
		"Other Income": sum(flt(row.get("other_income")) for row in data),
	}


def _chart(data: list[dict]) -> dict:
	totals = _component_totals(data)
	labels = [label for label, value in totals.items() if value]
	return {
		"data": {
			"labels": labels,
			"datasets": [{"name": _("Revenue"), "values": [totals[label] for label in labels]}],
		},
		"type": "bar",
		"colors": ["#6366f1"],
		"barOptions": {"stacked": 0},
		"fieldtype": "Currency",
	}


def _summary(data: list[dict]) -> list[dict]:
	return [
		{"label": _("Total Revenue"), "value": sum(flt(row.get("grand_total")) for row in data), "indicator": "Green", "datatype": "Currency"},
		{"label": _("Consultation Service Income"), "value": sum(flt(row.get("consultation_service_income")) for row in data), "indicator": "Blue", "datatype": "Currency"},
		{"label": _("Treatment Income"), "value": sum(flt(row.get("treatment_income")) for row in data), "indicator": "Orange", "datatype": "Currency"},
		{"label": _("Outstanding"), "value": sum(flt(row.get("outstanding_amount")) for row in data), "indicator": "Red", "datatype": "Currency"},
	]


def execute_revenue_summary(filters=None):
	filters = _filters(filters)
	data = _data(filters)
	return _columns(), data, None, _chart(data), _summary(data)
