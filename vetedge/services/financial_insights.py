from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, cint, cstr, flt, getdate, nowdate
from datetime import timedelta
from vetedge.services.financial_dataset import build_financial_dataset


def get_financial_insights(filters=None) -> dict:
	"""
	Shared Insight Engine for VetEdge/EdgeSuite financial analytics.
	Processes the unified financial dataset for current and comparable previous period.
	Returns a structured insights payload with consistent schemas for UI cards, alerts,
	composition, and concentration metrics.
	"""
	filters = frappe._dict(filters or {})
	
	# Resolve current dates
	to_date_str = filters.get("to_date") or nowdate()
	from_date_str = filters.get("from_date") or add_days(to_date_str, -30)
	
	to_date = getdate(to_date_str)
	from_date = getdate(from_date_str)
	
	# Calculate dynamic comparable previous period
	duration = (to_date - from_date).days + 1
	prev_to_date = from_date - timedelta(days=1)
	prev_from_date = prev_to_date - timedelta(days=duration - 1)
	
	prev_filters = filters.copy()
	prev_filters["from_date"] = prev_from_date.strftime("%Y-%m-%d")
	prev_filters["to_date"] = prev_to_date.strftime("%Y-%m-%d")
	
	# Fetch datasets
	current_dataset = build_financial_dataset(filters)
	prev_dataset = build_financial_dataset(prev_filters)
	
	# Single-pass aggregations
	current_agg = _aggregate_dataset(current_dataset, to_date)
	prev_agg = _aggregate_dataset(prev_dataset, prev_to_date)
	
	kpis = _build_summary_cards(current_agg, prev_agg, filters)
	collection_metrics = _build_collection_metrics(current_agg, prev_agg)
	composition = _build_revenue_composition(current_agg)
	outstanding_breakdowns = _build_outstanding_breakdowns(current_agg)
	health_indicators = _build_health_indicators(current_agg, from_date_str, to_date_str)
	alerts = _build_executive_alerts(current_agg, prev_agg)

	# Ensure backwards compatibility by injecting label field
	for card in kpis + collection_metrics + composition + health_indicators:
		if "title" in card and "label" not in card:
			card["label"] = card["title"]
	
	return {
		"kpis": kpis,
		"collection_metrics": collection_metrics,
		"revenue_composition": composition,
		"outstanding_breakdowns": outstanding_breakdowns,
		"health_indicators": health_indicators,
		"alerts": alerts,
		"dataset": current_agg["dataset"],
		"meta": {
			"current_period": {"from_date": from_date_str, "to_date": to_date_str},
			"previous_period": {"from_date": prev_filters["from_date"], "to_date": prev_filters["to_date"]},
		}
	}


def _aggregate_dataset(dataset, end_date) -> dict:
	"""
	Aggregates all metrics in a single iteration over the dataset.
	"""
	total_revenue = 0.0
	paid_revenue = 0.0
	outstanding_revenue = 0.0
	
	invoice_count = 0
	paid_invoice_count = 0
	unpaid_invoice_count = 0
	overdue_invoice_count = 0
	
	draft_invoice_count = 0
	draft_invoice_value = 0.0
	
	revenue_by_service = {}
	revenue_by_branch = {}
	revenue_by_customer = {}
	
	outstanding_by_branch = {}
	outstanding_by_service = {}
	outstanding_by_customer = {}
	outstanding_by_doctor = {}
	
	invoice_names = []
	paid_invoice_details = []
	outstanding_invoices = []
	
	for row in dataset:
		docstatus = row["docstatus"]
		grand_total = row["grand_total"]
		outstanding = row["outstanding_amount"]
		paid = row["paid_amount"]
		name = row["sales_invoice"]
		branch = row["branch"] or "Unassigned"
		service = row["service_source"] or "Other"
		customer = row["customer"]
		
		# Resolve linked doctor/practitioner details if available
		doctor = "Unassigned"
		if row.get("consultation_reference") and frappe.db.exists("Veterinary Consultation", row["consultation_reference"]):
			doctor = frappe.db.get_value("Veterinary Consultation", row["consultation_reference"], "consulting_practitioner") or "Unassigned"
		
		if docstatus == 0:  # Draft
			draft_invoice_count += 1
			draft_invoice_value += grand_total
		elif docstatus == 1:  # Submitted
			invoice_count += 1
			total_revenue += grand_total
			paid_revenue += paid
			outstanding_revenue += outstanding
			invoice_names.append(name)
			
			# Groupings for Revenue
			revenue_by_service[service] = revenue_by_service.get(service, 0.0) + grand_total
			revenue_by_branch[branch] = revenue_by_branch.get(branch, 0.0) + grand_total
			revenue_by_customer[customer] = revenue_by_customer.get(customer, 0.0) + grand_total
			
			# Collection statuses
			if outstanding <= 0:
				paid_invoice_count += 1
				paid_invoice_details.append({
					"name": name,
					"posting_date": row["posting_date"],
					"grand_total": grand_total
				})
			else:
				unpaid_invoice_count += 1
				due_date = row.get("due_date")
				is_overdue = due_date and getdate(due_date) < getdate(end_date)
				if is_overdue:
					overdue_invoice_count += 1
					
				# Groupings for Outstanding
				outstanding_by_branch[branch] = outstanding_by_branch.get(branch, 0.0) + outstanding
				outstanding_by_service[service] = outstanding_by_service.get(service, 0.0) + outstanding
				outstanding_by_customer[customer] = outstanding_by_customer.get(customer, 0.0) + outstanding
				outstanding_by_doctor[doctor] = outstanding_by_doctor.get(doctor, 0.0) + outstanding
				
				outstanding_invoices.append({
					"sales_invoice": name,
					"customer": customer,
					"outstanding_amount": outstanding,
					"days_overdue": (getdate(end_date) - getdate(due_date)).days if due_date else 0
				})

	# Bulk resolve payment days to avoid N+1 query loops
	avg_days_payment = _calculate_average_payment_days(paid_invoice_details)

	return {
		"total_revenue": total_revenue,
		"paid_revenue": paid_revenue,
		"outstanding_revenue": outstanding_revenue,
		"invoice_count": invoice_count,
		"paid_invoice_count": paid_invoice_count,
		"unpaid_invoice_count": unpaid_invoice_count,
		"overdue_invoice_count": overdue_invoice_count,
		"draft_invoice_count": draft_invoice_count,
		"draft_invoice_value": draft_invoice_value,
		"revenue_by_service": revenue_by_service,
		"revenue_by_branch": revenue_by_branch,
		"revenue_by_customer": revenue_by_customer,
		"outstanding_by_branch": outstanding_by_branch,
		"outstanding_by_service": outstanding_by_service,
		"outstanding_by_customer": outstanding_by_customer,
		"outstanding_by_doctor": outstanding_by_doctor,
		"outstanding_invoices": outstanding_invoices,
		"avg_days_payment": avg_days_payment,
		"dataset": dataset
	}


def _calculate_average_payment_days(paid_invoices) -> float:
	invoice_names = [inv["name"] for inv in paid_invoices]
	if not invoice_names or not frappe.db.exists("DocType", "Payment Entry Reference"):
		return 0.0
	
	refs = frappe.get_all(
		"Payment Entry Reference",
		filters={"reference_doctype": "Sales Invoice", "reference_name": ("in", invoice_names)},
		fields=["reference_name", "parent"],
	)
	parent_names = [r.parent for r in refs if r.parent]
	if not parent_names:
		return 0.0
		
	payments = frappe.get_all(
		"Payment Entry",
		filters={"name": ("in", parent_names), "docstatus": 1},
		fields=["name", "posting_date"]
	)
	pay_dates = {p.name: p.posting_date for p in payments}
	
	inv_pay_dates = {}
	for r in refs:
		p_date = pay_dates.get(r.parent)
		if p_date:
			name = r.reference_name
			if name not in inv_pay_dates or p_date < inv_pay_dates[name]:
				inv_pay_dates[name] = p_date

	total_days = 0.0
	count = 0
	for inv in paid_invoices:
		p_date = inv_pay_dates.get(inv["name"])
		if p_date:
			days = (getdate(p_date) - getdate(inv["posting_date"])).days
			total_days += max(days, 0)
			count += 1
			
	return round(total_days / count, 1) if count > 0 else 0.0


def _build_trend(current, previous) -> dict:
	if not previous:
		return {"direction": "up" if current > 0 else "flat", "percentage": 100.0 if current > 0 else 0.0}
	diff = float(current) - float(previous)
	pct = round((diff / float(previous)) * 100.0, 1)
	if pct > 0:
		return {"direction": "up", "percentage": pct}
	elif pct < 0:
		return {"direction": "down", "percentage": abs(pct)}
	else:
		return {"direction": "flat", "percentage": 0.0}


def _build_summary_cards(current, prev, filters) -> list[dict]:
	branch_filter = {"branch": filters.get("branch")} if filters.get("branch") else {}
	
	return [
		{
			"id": "total_revenue",
			"title": _("Total Revenue"),
			"value": current["total_revenue"],
			"secondary_value": f"{current['invoice_count']} Invoices",
			"trend": _build_trend(current["total_revenue"], prev["total_revenue"]),
			"action": {"type": "report", "target": "Revenue Summary", "filters": branch_filter},
			"tooltip": _("Total value of all submitted invoices in this period."),
			"severity": "success" if current["total_revenue"] >= prev["total_revenue"] else "warning",
			"category": "summary"
		},
		{
			"id": "paid_revenue",
			"title": _("Paid Revenue"),
			"value": current["paid_revenue"],
			"secondary_value": f"{current['paid_invoice_count']} Fully Paid Invoices",
			"trend": _build_trend(current["paid_revenue"], prev["paid_revenue"]),
			"action": {"type": "report", "target": "Revenue Summary", "filters": branch_filter},
			"tooltip": _("Total revenue collected for submitted invoices."),
			"severity": "success",
			"category": "summary"
		},
		{
			"id": "outstanding_revenue",
			"title": _("Outstanding Revenue"),
			"value": current["outstanding_revenue"],
			"secondary_value": f"{current['overdue_invoice_count']} Overdue Invoices / {current['unpaid_invoice_count']} Unpaid",
			"trend": _build_trend(current["outstanding_revenue"], prev["outstanding_revenue"]),
			"action": {"type": "report", "target": "Unpaid Invoice Report", "filters": branch_filter},
			"tooltip": _("Outstanding balance remaining on all submitted invoices."),
			"severity": "danger" if current["outstanding_revenue"] > prev["outstanding_revenue"] else "info",
			"category": "summary"
		},
		{
			"id": "draft_invoices",
			"title": _("Draft / Pending Invoices"),
			"label": _("Draft / Pending Invoices"),
			"value": current["draft_invoice_count"],
			"secondary_value": f"{frappe.format_value(current['draft_invoice_value'], {'fieldtype': 'Currency'})} Value",
			"trend": _build_trend(current["draft_invoice_count"], prev["draft_invoice_count"]),
			"action": {"type": "report", "target": "Unpaid Invoice Report", "filters": dict(branch_filter, status="Draft")},
			"tooltip": _("Total value of invoices currently in Draft status."),
			"severity": "warning" if current["draft_invoice_count"] > 0 else "info",
			"category": "summary"
		},
		{
			"id": "payments_received",
			"title": _("Payments Received"),
			"value": current["paid_revenue"],
			"secondary_value": f"Avg payment amount: {frappe.format_value(current['paid_revenue'] / current['paid_invoice_count'] if current['paid_invoice_count'] else 0.0, {'fieldtype': 'Currency'})}",
			"trend": _build_trend(current["paid_revenue"], prev["paid_revenue"]),
			"action": {"type": "report", "target": "Revenue Summary", "filters": branch_filter},
			"tooltip": _("Total payments collected for invoices submitted in this window."),
			"severity": "info",
			"category": "summary"
		}
	]


def _build_collection_metrics(current, prev) -> list[dict]:
	curr_cr = (current["paid_revenue"] / current["total_revenue"] * 100.0) if current["total_revenue"] else 0.0
	prev_cr = (prev["paid_revenue"] / prev["total_revenue"] * 100.0) if prev["total_revenue"] else 0.0
	
	curr_aiv = (current["total_revenue"] / current["invoice_count"]) if current["invoice_count"] else 0.0
	prev_aiv = (prev["total_revenue"] / prev["invoice_count"]) if prev["invoice_count"] else 0.0

	curr_aob = (current["outstanding_revenue"] / current["unpaid_invoice_count"]) if current["unpaid_invoice_count"] else 0.0
	prev_aob = (prev["outstanding_revenue"] / prev["unpaid_invoice_count"]) if prev["unpaid_invoice_count"] else 0.0

	return [
		{
			"id": "collection_rate",
			"title": _("Collection Rate"),
			"value": curr_cr,
			"secondary_value": f"{round(curr_cr, 1)}%",
			"trend": _build_trend(curr_cr, prev_cr),
			"tooltip": _("Collected revenue as a percentage of total submitted revenue."),
			"severity": "success" if curr_cr >= 80.0 else ("warning" if curr_cr >= 50.0 else "danger"),
			"category": "collection"
		},
		{
			"id": "avg_invoice_value",
			"title": _("Average Invoice Value"),
			"value": curr_aiv,
			"secondary_value": None,
			"trend": _build_trend(curr_aiv, prev_aiv),
			"tooltip": _("Average value of a submitted Sales Invoice."),
			"severity": "info",
			"category": "collection"
		},
		{
			"id": "avg_outstanding_balance",
			"title": _("Average Outstanding Balance"),
			"value": curr_aob,
			"secondary_value": None,
			"trend": _build_trend(curr_aob, prev_aob),
			"tooltip": _("Average outstanding balance on unpaid invoices."),
			"severity": "warning" if curr_aob > prev_aob else "info",
			"category": "collection"
		},
		{
			"id": "avg_days_payment",
			"title": _("Average Days to Payment"),
			"value": current["avg_days_payment"],
			"secondary_value": f"{current['avg_days_payment']} Days",
			"trend": _build_trend(current["avg_days_payment"], prev["avg_days_payment"]),
			"tooltip": _("Average time taken to fully collect payments for submitted invoices."),
			"severity": "success" if current["avg_days_payment"] <= 7.0 else ("warning" if current["avg_days_payment"] <= 30.0 else "danger"),
			"category": "collection"
		}
	]


def _build_revenue_composition(current) -> list[dict]:
	total = current["total_revenue"]
	composition = []
	for service, val in current["revenue_by_service"].items():
		pct = (val / total * 100.0) if total else 0.0
		composition.append({
			"id": f"rev_comp_{service.lower()}",
			"title": service,
			"value": val,
			"secondary_value": f"{round(pct, 1)}% of Revenue",
			"trend": None,
			"tooltip": f"Total revenue generated from {service} services.",
			"severity": "info",
			"category": "composition"
		})
	return sorted(composition, key=lambda x: x["value"], reverse=True)


def _build_outstanding_breakdowns(current) -> dict:
	top_5 = sorted(current["outstanding_invoices"], key=lambda x: x["outstanding_amount"], reverse=True)[:5]
	
	# Top 5 lists
	outstanding_by_branch = sorted(
		[{"name": k, "value": v} for k, v in current["outstanding_by_branch"].items()],
		key=lambda x: x["value"], reverse=True
	)
	outstanding_by_service = sorted(
		[{"name": k, "value": v} for k, v in current["outstanding_by_service"].items()],
		key=lambda x: x["value"], reverse=True
	)
	outstanding_by_customer = sorted(
		[{"name": k, "value": v} for k, v in current["outstanding_by_customer"].items()],
		key=lambda x: x["value"], reverse=True
	)
	outstanding_by_doctor = sorted(
		[{"name": k, "value": v} for k, v in current["outstanding_by_doctor"].items()],
		key=lambda x: x["value"], reverse=True
	)

	return {
		"top_outstanding_balances": top_5,
		"by_branch": outstanding_by_branch,
		"by_service": outstanding_by_service,
		"by_customer": outstanding_by_customer,
		"by_doctor": outstanding_by_doctor
	}


def _build_health_indicators(current, from_date, to_date) -> list[dict]:
	# Billed consultations vs total consultations
	billed_c_count = 0
	total_c_count = 0
	if frappe.db.exists("DocType", "Veterinary Consultation"):
		total_c_count = frappe.db.count(
			"Veterinary Consultation",
			filters={"docstatus": ("<", 2), "consultation_datetime": ("between", [from_date, to_date])}
		)
		billed_c_count = len({
			row["consultation_reference"] for row in current["dataset"]
			if row["consultation_reference"] and row["docstatus"] == 1
		})
	
	billing_rate = (billed_c_count / total_c_count * 100.0) if total_c_count else 100.0
	payment_completion_rate = (current["paid_invoice_count"] / current["invoice_count"] * 100.0) if current["invoice_count"] else 100.0

	# Find maximum entries for concentration
	max_branch = max(current["revenue_by_branch"].items(), key=lambda x: x[1], default=("None", 0.0))
	max_service = max(current["revenue_by_service"].items(), key=lambda x: x[1], default=("None", 0.0))
	max_customer = max(current["revenue_by_customer"].items(), key=lambda x: x[1], default=("None", 0.0))
	
	total = current["total_revenue"]
	branch_pct = (max_branch[1] / total * 100.0) if total else 0.0
	service_pct = (max_service[1] / total * 100.0) if total else 0.0
	customer_pct = (max_customer[1] / total * 100.0) if total else 0.0

	return [
		{
			"id": "billing_completion_rate",
			"title": _("Billing Completion Rate"),
			"value": billing_rate,
			"secondary_value": f"{billed_c_count} of {total_c_count} Consultations Invoiced",
			"trend": None,
			"tooltip": _("Percentage of finalized clinical consultations that have been invoiced."),
			"severity": "success" if billing_rate >= 90.0 else ("warning" if billing_rate >= 75.0 else "danger"),
			"category": "health"
		},
		{
			"id": "payment_completion_rate",
			"title": _("Payment Completion Rate"),
			"value": payment_completion_rate,
			"secondary_value": f"{current['paid_invoice_count']} of {current['invoice_count']} Invoices Paid",
			"trend": None,
			"tooltip": _("Percentage of submitted invoices that are fully collected."),
			"severity": "success" if payment_completion_rate >= 90.0 else ("warning" if payment_completion_rate >= 75.0 else "danger"),
			"category": "health"
		},
		{
			"id": "revenue_concentration",
			"title": _("Revenue Concentration"),
			"value": f"Branch: {max_branch[0]} ({round(branch_pct, 1)}%)",
			"secondary_value": f"Service: {max_service[0]} ({round(service_pct, 1)}%) / Customer: {max_customer[0]} ({round(customer_pct, 1)}%)",
			"trend": None,
			"tooltip": _("Highlights concentration of revenue generation across dimensions."),
			"severity": "warning" if branch_pct > 50.0 or service_pct > 50.0 or customer_pct > 30.0 else "info",
			"category": "health"
		}
	]


def _build_executive_alerts(current, prev) -> list[dict]:
	alerts = []

	# Alert 1: Outstanding growth
	if prev["outstanding_revenue"] > 0:
		out_pct = ((current["outstanding_revenue"] - prev["outstanding_revenue"]) / prev["outstanding_revenue"]) * 100.0
		if out_pct >= 10.0:
			alerts.append({
				"id": "alert_outstanding_growth",
				"title": _("Outstanding Revenue Growth"),
				"description": _("Outstanding revenue increased by {0}% compared to the previous period.").format(round(out_pct, 1)),
				"supporting_metric": f"{frappe.format_value(current['outstanding_revenue'], {'fieldtype': 'Currency'})}",
				"secondary_value": f"{frappe.format_value(current['outstanding_revenue'], {'fieldtype': 'Currency'})} Outstanding",
				"severity": "danger",
				"action": {"type": "report", "target": "Unpaid Invoice Report"}
			})

	# Alert 2: Overdue invoice count
	if current["overdue_invoice_count"] > 0:
		alerts.append({
			"id": "alert_overdue_invoices",
			"title": _("Overdue Accounts Receivable"),
			"description": _("There are {0} submitted invoices that are past their due dates.").format(current["overdue_invoice_count"]),
			"supporting_metric": f"{current['overdue_invoice_count']} Overdue",
			"secondary_value": f"{current['overdue_invoice_count']} Overdue Invoices",
			"severity": "danger",
			"action": {"type": "report", "target": "Unpaid Invoice Report"}
		})

	# Alert 3: Dominant branch
	total = current["total_revenue"]
	if total > 0:
		for branch, val in current["revenue_by_branch"].items():
			pct = (val / total) * 100.0
			if pct >= 40.0 and branch != "Unassigned":
				alerts.append({
					"id": "alert_branch_concentration",
					"title": _("Branch Revenue Concentration"),
					"description": _("Branch {0} generated {1}% of practice revenue.").format(branch, round(pct, 1)),
					"supporting_metric": f"{round(pct, 1)}%",
					"secondary_value": f"{round(pct, 1)}% Practice Total",
					"severity": "warning"
				})

	# Alert 4: Service growth highlights
	for service, val in current["revenue_by_service"].items():
		prev_val = prev["revenue_by_service"].get(service, 0.0)
		if prev_val > 500.0:  # Only count meaningful baseline values
			growth_pct = ((val - prev_val) / prev_val) * 100.0
			if growth_pct >= 20.0:
				alerts.append({
					"id": f"alert_growth_{service.lower()}",
					"title": _("{0} Revenue Growth").format(service),
					"description": _("{0} revenue grew by {1}% compared to the previous window.").format(service, round(growth_pct, 1)),
					"supporting_metric": f"+{round(growth_pct, 1)}%",
					"secondary_value": f"+{round(growth_pct, 1)}% Growth",
					"severity": "success"
				})

	# Alert 5: Critical payment collection times
	if current["avg_days_payment"] >= 15.0:
		alerts.append({
			"id": "alert_slow_collections",
			"title": _("Slow Payment Collections"),
			"description": _("Payment collection times average {0} days, slowing cash flow.").format(current["avg_days_payment"]),
			"supporting_metric": f"{current['avg_days_payment']} Days",
			"secondary_value": f"{current['avg_days_payment']} Days average",
			"severity": "warning"
		})

	return alerts
