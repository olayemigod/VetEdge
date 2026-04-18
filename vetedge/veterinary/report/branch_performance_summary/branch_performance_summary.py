from __future__ import annotations

from frappe import _
from frappe.utils import flt

from vetedge.services.financial_dashboard import (
	get_branch_performance_data,
	get_report_chart,
	require_read_permission,
)


def execute(filters=None):
	require_read_permission("Sales Invoice")

	columns = get_columns()
	data = get_branch_performance_data(filters)
	chart = get_report_chart(filters)
	report_summary = get_report_summary(data)

	return columns, data, None, chart, report_summary


def get_columns():
	return [
		{
			"fieldname": "cost_center",
			"label": _("Cost Center"),
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 220,
		},
		{
			"fieldname": "branch",
			"label": _("Branch"),
			"fieldtype": "Link",
			"options": "Branch",
			"width": 180,
		},
		{"fieldname": "invoice_count", "label": _("Invoices"), "fieldtype": "Int", "width": 100},
		{"fieldname": "revenue", "label": _("Revenue"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "paid_amount", "label": _("Paid"), "fieldtype": "Currency", "width": 140},
		{
			"fieldname": "outstanding_amount",
			"label": _("Outstanding"),
			"fieldtype": "Currency",
			"width": 140,
		},
		{
			"fieldname": "average_invoice_value",
			"label": _("Average Invoice"),
			"fieldtype": "Currency",
			"width": 150,
		},
	]


def get_report_summary(data):
	total_revenue = flt(sum(row.get("revenue") for row in data), 2)
	total_paid = flt(sum(row.get("paid_amount") for row in data), 2)
	total_outstanding = flt(sum(row.get("outstanding_amount") for row in data), 2)

	return [
		{"label": _("Revenue"), "value": total_revenue, "indicator": "Green", "datatype": "Currency"},
		{"label": _("Paid"), "value": total_paid, "indicator": "Blue", "datatype": "Currency"},
		{
			"label": _("Outstanding"),
			"value": total_outstanding,
			"indicator": "Orange" if total_outstanding else "Green",
			"datatype": "Currency",
		},
	]
