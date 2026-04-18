from __future__ import annotations

from datetime import date

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_first_day, getdate, nowdate


UNASSIGNED_COST_CENTER = "Unassigned"
DEFAULT_CHART = "daily_revenue_trend"


@frappe.whitelist()
def get_today_revenue(filters=None):
	require_read_permission("Sales Invoice")
	today = nowdate()
	return currency_card(
		get_sales_invoice_total(today, today, get_filter_value(filters, "cost_center")),
		{"from_date": today, "to_date": today},
	)


@frappe.whitelist()
def get_week_revenue(filters=None):
	require_read_permission("Sales Invoice")
	today = getdate(nowdate())
	from_date = add_days(today, -today.weekday())
	return currency_card(
		get_sales_invoice_total(from_date, today, get_filter_value(filters, "cost_center")),
		{"from_date": from_date, "to_date": today},
	)


@frappe.whitelist()
def get_month_revenue(filters=None):
	require_read_permission("Sales Invoice")
	today = nowdate()
	from_date = get_first_day(today)
	return currency_card(
		get_sales_invoice_total(from_date, today, get_filter_value(filters, "cost_center")),
		{"from_date": from_date, "to_date": today},
	)


@frappe.whitelist()
def get_outstanding_receivables(filters=None):
	require_read_permission("Sales Invoice")
	return currency_card(
		get_outstanding_total(get_filter_value(filters, "cost_center")),
		{"from_date": None, "to_date": None},
	)


@frappe.whitelist()
def get_payments_today(filters=None):
	require_read_permission("Payment Entry")
	today = nowdate()
	return currency_card(get_payment_total(today, today), {"from_date": today, "to_date": today})


def currency_card(value: float, route_options: dict | None = None) -> dict:
	return {
		"value": flt(value, 2),
		"fieldtype": "Currency",
		"route": ["query-report", "Branch Performance Summary"],
		"route_options": route_options or {},
	}


def get_filter_value(filters, fieldname: str):
	if not filters:
		return None

	if isinstance(filters, str):
		filters = frappe.parse_json(filters)

	return filters.get(fieldname)


def require_read_permission(doctype: str) -> None:
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("Not permitted to read {0}.").format(_(doctype)), frappe.PermissionError)


def default_date_range(filters=None) -> tuple[date, date]:
	filters = frappe._dict(filters or {})
	to_date = getdate(filters.get("to_date") or nowdate())
	from_date = getdate(filters.get("from_date") or get_first_day(to_date))
	return from_date, to_date


def get_sales_invoice_total(from_date, to_date, cost_center: str | None = None) -> float:
	if cost_center:
		query = """
			SELECT COALESCE(SUM(sii.base_net_amount), 0)
			FROM `tabSales Invoice` si
			INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
			WHERE si.docstatus = 1
				AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
				AND sii.cost_center = %(cost_center)s
		"""
	else:
		query = """
			SELECT COALESCE(SUM(si.base_grand_total), 0)
			FROM `tabSales Invoice` si
			WHERE si.docstatus = 1
				AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
		"""

	return flt(
		frappe.db.sql(
			query,
			{"from_date": from_date, "to_date": to_date, "cost_center": cost_center},
		)[0][0],
		2,
	)


def get_outstanding_total(cost_center: str | None = None) -> float:
	if cost_center:
		rows = get_branch_performance_data({"cost_center": cost_center})
		return flt(sum(row.get("outstanding_amount") for row in rows), 2)

	return flt(
		frappe.db.sql(
			"""
			SELECT COALESCE(SUM(si.outstanding_amount), 0)
			FROM `tabSales Invoice` si
			WHERE si.docstatus = 1
				AND si.outstanding_amount > 0
			"""
		)[0][0],
		2,
	)


def get_payment_total(from_date, to_date) -> float:
	return flt(
		frappe.db.sql(
			"""
			SELECT COALESCE(SUM(pe.base_paid_amount), 0)
			FROM `tabPayment Entry` pe
			WHERE pe.docstatus = 1
				AND pe.payment_type = 'Receive'
				AND pe.posting_date BETWEEN %(from_date)s AND %(to_date)s
			""",
			{"from_date": from_date, "to_date": to_date},
		)[0][0],
		2,
	)


def get_branch_performance_data(filters=None) -> list[frappe._dict]:
	filters = frappe._dict(filters or {})
	from_date, to_date = default_date_range(filters)
	conditions = ["si.docstatus = 1", "si.posting_date BETWEEN %(from_date)s AND %(to_date)s"]
	params = {"from_date": from_date, "to_date": to_date}

	if filters.get("cost_center"):
		conditions.append("sii.cost_center = %(cost_center)s")
		params["cost_center"] = filters.get("cost_center")

	where_clause = " AND ".join(conditions)
	rows = frappe.db.sql(
		f"""
		SELECT
			invoice_cost_centers.cost_center,
			COUNT(DISTINCT invoice_cost_centers.invoice) AS invoice_count,
			COALESCE(SUM(invoice_cost_centers.revenue), 0) AS revenue,
			COALESCE(SUM(invoice_cost_centers.paid_amount), 0) AS paid_amount,
			COALESCE(SUM(invoice_cost_centers.outstanding_amount), 0) AS outstanding_amount
		FROM (
			SELECT
				si.name AS invoice,
				COALESCE(NULLIF(sii.cost_center, ''), %(unassigned_cost_center)s) AS cost_center,
				COALESCE(SUM(sii.base_net_amount), 0) AS revenue,
				COALESCE(
					MAX(si.base_grand_total - si.outstanding_amount)
					* SUM(sii.base_net_amount)
					/ NULLIF(MAX(invoice_totals.invoice_revenue), 0),
					0
				) AS paid_amount,
				COALESCE(
					MAX(si.outstanding_amount)
					* SUM(sii.base_net_amount)
					/ NULLIF(MAX(invoice_totals.invoice_revenue), 0),
					0
				) AS outstanding_amount
			FROM `tabSales Invoice` si
			INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
			INNER JOIN (
				SELECT
					parent,
					COALESCE(SUM(base_net_amount), 0) AS invoice_revenue
				FROM `tabSales Invoice Item`
				GROUP BY parent
			) invoice_totals ON invoice_totals.parent = si.name
			WHERE {where_clause}
			GROUP BY si.name, COALESCE(NULLIF(sii.cost_center, ''), %(unassigned_cost_center)s)
		) invoice_cost_centers
		GROUP BY invoice_cost_centers.cost_center
		ORDER BY revenue DESC
		""",
		{**params, "unassigned_cost_center": UNASSIGNED_COST_CENTER},
		as_dict=True,
	)

	branch_by_cost_center = get_branch_by_cost_center()
	for row in rows:
		row.branch = branch_by_cost_center.get(row.cost_center)
		row.revenue = flt(row.revenue, 2)
		row.paid_amount = flt(row.paid_amount, 2)
		row.outstanding_amount = flt(row.outstanding_amount, 2)
		row.average_invoice_value = flt(row.revenue / row.invoice_count, 2) if row.invoice_count else 0

	return rows


def get_branch_by_cost_center() -> dict[str, str]:
	if not frappe.db.table_exists("Branch"):
		return {}

	branch_meta = frappe.get_meta("Branch")
	fields = ["name"]
	for fieldname in ("cost_center", "vetedge_cost_center"):
		if branch_meta.has_field(fieldname):
			fields.append(fieldname)

	if len(fields) == 1:
		return {}

	branch_by_cost_center = {}
	for branch in frappe.get_all("Branch", fields=fields):
		for fieldname in fields:
			if fieldname == "name":
				continue
			if branch.get(fieldname):
				branch_by_cost_center[branch.get(fieldname)] = branch.name

	return branch_by_cost_center


def get_daily_revenue_chart(filters=None) -> dict:
	filters = frappe._dict(filters or {})
	from_date, to_date = default_date_range(filters)
	conditions = ["si.docstatus = 1", "si.posting_date BETWEEN %(from_date)s AND %(to_date)s"]
	params = {"from_date": from_date, "to_date": to_date}

	if filters.get("cost_center"):
		conditions.append("sii.cost_center = %(cost_center)s")
		params["cost_center"] = filters.get("cost_center")
		revenue_expression = "SUM(sii.base_net_amount)"
		join_clause = "INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name"
	else:
		revenue_expression = "SUM(si.base_grand_total)"
		join_clause = ""

	rows = frappe.db.sql(
		f"""
		SELECT si.posting_date, COALESCE({revenue_expression}, 0) AS revenue
		FROM `tabSales Invoice` si
		{join_clause}
		WHERE {" AND ".join(conditions)}
		GROUP BY si.posting_date
		ORDER BY si.posting_date
		""",
		params,
		as_dict=True,
	)

	return chart(
		[row.posting_date for row in rows],
		[{"name": _("Revenue"), "values": [flt(row.revenue, 2) for row in rows]}],
		"line",
	)


def get_revenue_by_cost_center_chart(filters=None) -> dict:
	rows = get_branch_performance_data(filters)
	return chart(
		[row.cost_center for row in rows],
		[{"name": _("Revenue"), "values": [row.revenue for row in rows]}],
		"bar",
	)


def get_revenue_by_service_type_chart(filters=None) -> dict:
	rows = get_revenue_by_service_type(filters)
	return chart(
		[row.service_type for row in rows],
		[{"name": _("Revenue"), "values": [row.revenue for row in rows]}],
		"bar",
	)


def get_paid_vs_outstanding_chart(filters=None) -> dict:
	rows = get_branch_performance_data(filters)
	return chart(
		[_("Paid"), _("Outstanding")],
		[{"name": _("Amount"), "values": [sum(row.paid_amount for row in rows), sum(row.outstanding_amount for row in rows)]}],
		"donut",
	)


def get_payment_method_breakdown_chart(filters=None) -> dict:
	rows = get_payment_method_breakdown(filters)
	return chart(
		[row.mode_of_payment for row in rows],
		[{"name": _("Payments"), "values": [row.amount for row in rows]}],
		"donut",
	)


def get_revenue_by_service_type(filters=None) -> list[frappe._dict]:
	filters = frappe._dict(filters or {})
	from_date, to_date = default_date_range(filters)
	conditions = ["si.docstatus = 1", "si.posting_date BETWEEN %(from_date)s AND %(to_date)s"]
	params = {"from_date": from_date, "to_date": to_date}

	if filters.get("cost_center"):
		conditions.append("sii.cost_center = %(cost_center)s")
		params["cost_center"] = filters.get("cost_center")

	rows = frappe.db.sql(
		f"""
		SELECT
			COALESCE(vst.service_type_name, %(unmapped)s) AS service_type,
			COALESCE(SUM(sii.base_net_amount), 0) AS revenue
		FROM `tabSales Invoice` si
		INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		LEFT JOIN `tabVeterinary Service Type` vst ON vst.default_item = sii.item_code
		WHERE {" AND ".join(conditions)}
		GROUP BY COALESCE(vst.service_type_name, %(unmapped)s)
		ORDER BY revenue DESC
		""",
		{**params, "unmapped": _("Unmapped Service")},
		as_dict=True,
	)

	for row in rows:
		row.revenue = flt(row.revenue, 2)

	return rows


def get_payment_method_breakdown(filters=None) -> list[frappe._dict]:
	require_read_permission("Payment Entry")
	filters = frappe._dict(filters or {})
	from_date, to_date = default_date_range(filters)
	rows = frappe.db.sql(
		"""
		SELECT
			COALESCE(NULLIF(pe.mode_of_payment, ''), %(unspecified)s) AS mode_of_payment,
			COALESCE(SUM(pe.base_paid_amount), 0) AS amount
		FROM `tabPayment Entry` pe
		WHERE pe.docstatus = 1
			AND pe.payment_type = 'Receive'
			AND pe.posting_date BETWEEN %(from_date)s AND %(to_date)s
		GROUP BY COALESCE(NULLIF(pe.mode_of_payment, ''), %(unspecified)s)
		ORDER BY amount DESC
		""",
		{"from_date": from_date, "to_date": to_date, "unspecified": _("Unspecified")},
		as_dict=True,
	)

	for row in rows:
		row.amount = flt(row.amount, 2)

	return rows


def get_report_chart(filters=None) -> dict | None:
	filters = frappe._dict(filters or {})
	chart_name = filters.get("chart") or DEFAULT_CHART
	chart_map = {
		"daily_revenue_trend": get_daily_revenue_chart,
		"revenue_by_cost_center": get_revenue_by_cost_center_chart,
		"revenue_by_service_type": get_revenue_by_service_type_chart,
		"paid_vs_outstanding": get_paid_vs_outstanding_chart,
		"payment_method_breakdown": get_payment_method_breakdown_chart,
	}
	return chart_map.get(chart_name, get_daily_revenue_chart)(filters)


def chart(labels: list, datasets: list[dict], chart_type: str) -> dict:
	return {
		"data": {
			"labels": [str(label) for label in labels],
			"datasets": datasets,
		},
		"type": chart_type,
	}
