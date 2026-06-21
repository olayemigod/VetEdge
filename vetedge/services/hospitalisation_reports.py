from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path

import frappe
from frappe.utils import cint, flt, get_datetime, getdate, now_datetime

from vetedge.services.hospitalisation import build_hospitalisation_discharge_readiness

HOSPITALISATION_DOCTYPE = "Veterinary Hospitalisation"
CARE_LOCATION_DOCTYPE = "Veterinary Care Location"
CARE_LOCATION_LOG_DOCTYPE = "Veterinary Care Location Occupancy Log"
ACTIVE_STATUSES = {"Admitted", "Under Care", "Ready for Discharge"}
PENDING_CHARGE_STATUSES = {"Pending Invoice", "Pending Charge", "Not Invoiced", "Draft"}


def normalize_filters(filters=None) -> frappe._dict:
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	return frappe._dict(filters or {})


def get_hospitalisation_base_fields() -> list[str]:
	return [
		"name",
		"patient",
		"customer",
		"service_branch",
		"admission_datetime",
		"discharge_datetime",
		"status",
		"care_level",
		"care_location",
		"attending_veterinarian",
		"invoice_status",
		"payment_gate_status",
		"sales_invoice",
		"follow_up_date",
		"discharge_summary",
		"modified",
	]


def get_hospitalisation_docs(filters=None, active_only: bool = False) -> list:
	filters = normalize_filters(filters)
	query_filters = {}
	if filters.get("branch"):
		query_filters["service_branch"] = filters.branch
	if filters.get("care_level"):
		query_filters["care_level"] = filters.care_level
	if filters.get("care_location"):
		query_filters["care_location"] = filters.care_location
	if filters.get("attending_veterinarian"):
		query_filters["attending_veterinarian"] = filters.attending_veterinarian
	if filters.get("owner"):
		query_filters["customer"] = filters.owner
	if filters.get("patient"):
		query_filters["patient"] = filters.patient
	if filters.get("invoice_status"):
		query_filters["invoice_status"] = filters.invoice_status
	if filters.get("status"):
		query_filters["status"] = filters.status
	elif active_only:
		query_filters["status"] = ["in", sorted(ACTIVE_STATUSES)]

	names = frappe.get_all(HOSPITALISATION_DOCTYPE, filters=query_filters, fields=["name"], order_by="admission_datetime desc") or []
	docs = []
	for row in names:
		doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, row.get("name"))
		if not hospitalisation_matches_date_filters(doc, filters):
			continue
		docs.append(doc)
	return docs


def hospitalisation_matches_date_filters(doc, filters) -> bool:
	admission = doc.get("admission_datetime")
	if not admission:
		return True
	admission_date = getdate(admission)
	from_date = filters.get("admission_date_from") or filters.get("from_date")
	to_date = filters.get("admission_date_to") or filters.get("to_date")
	if from_date and admission_date < getdate(from_date):
		return False
	if to_date and admission_date > getdate(to_date):
		return False
	return True


def days_admitted(doc) -> int:
	start = doc.get("admission_datetime")
	if not start:
		return 0
	end = doc.get("discharge_datetime") or now_datetime()
	start_dt = get_datetime(start)
	end_dt = get_datetime(end)
	if end_dt < start_dt:
		return 0
	return max((end_dt.date() - start_dt.date()).days + 1, 1)


def get_latest_activity_datetime(doc):
	latest = None
	for activity in doc.get("activities") or []:
		activity_dt = activity.get("activity_datetime")
		if activity_dt and (not latest or get_datetime(activity_dt) > get_datetime(latest)):
			latest = activity_dt
	return latest


def get_charge_totals(doc) -> dict:
	pending = invoiced = cancelled = 0.0
	missing_price_count = 0
	missing_price_amount = 0.0
	breakdown = defaultdict(float)
	for row in doc.get("charge_items") or []:
		qty = flt(row.get("qty")) or 1
		rate = flt(row.get("rate"))
		amount = flt(row.get("amount")) or qty * rate
		category = row.get("charge_category") or row.get("activity_type") or "Other"
		if row.get("billing_status") == "Invoiced":
			invoiced += amount
		elif row.get("billing_status") == "Cancelled":
			cancelled += amount
		else:
			pending += amount
			if row.get("item") and (rate <= 0 or amount <= 0):
				missing_price_count += 1
				missing_price_amount += amount
		breakdown[category] += amount
	non_billable_count = sum(1 for activity in doc.get("activities") or [] if not cint(activity.get("billable")))
	return {
		"total_charges": pending + invoiced + cancelled,
		"pending_charges": pending,
		"invoiced_charges": invoiced,
		"cancelled_charges": cancelled,
		"missing_price_count": missing_price_count,
		"missing_price_amount": missing_price_amount,
		"non_billable_count": non_billable_count,
		"breakdown": dict(breakdown),
	}


def get_pending_stock_count(doc) -> int:
	return sum(
		1
		for row in doc.get("activities") or []
		if cint(row.get("stock_affecting")) and row.get("stock_status") != "Posted" and not row.get("stock_entry")
	)


def get_pending_billable_without_charge_count(doc) -> int:
	charge_sources = {row.get("source_activity") for row in doc.get("charge_items") or [] if row.get("billing_status") != "Cancelled"}
	return sum(
		1
		for row in doc.get("activities") or []
		if cint(row.get("billable")) and row.get("billing_status") not in {"Charged", "Cancelled"} and (row.get("activity_reference") or row.get("name")) not in charge_sources
	)


def get_discharge_readiness_summary(doc) -> str:
	readiness = build_hospitalisation_discharge_readiness(doc)
	messages = readiness.get("messages") or readiness.get("warnings") or []
	if readiness.get("can_discharge"):
		return "Ready" if not messages else "Ready with warnings: " + "; ".join(messages)
	return "; ".join(messages) or "Not ready"


def get_invoice_payment_summary(doc) -> dict:
	invoice = doc.get("sales_invoice")
	if not invoice or not frappe.db.exists("Sales Invoice", invoice):
		return {"payment_status": "Not Invoiced", "outstanding_amount": 0}
	try:
		row = frappe.db.get_value("Sales Invoice", invoice, ["status", "outstanding_amount"], as_dict=True) or {}
		return {"payment_status": row.get("status") or doc.get("invoice_status"), "outstanding_amount": flt(row.get("outstanding_amount"))}
	except Exception:
		return {"payment_status": doc.get("invoice_status"), "outstanding_amount": 0}


ACTIVE_HOSPITALISATIONS_COLUMNS = [
	{"label": "Hospitalisation", "fieldname": "hospitalisation", "fieldtype": "Link", "options": HOSPITALISATION_DOCTYPE, "width": 170},
	{"label": "Patient", "fieldname": "patient", "fieldtype": "Link", "options": "Veterinary Patient", "width": 160},
	{"label": "Pet Owner", "fieldname": "owner", "fieldtype": "Link", "options": "Customer", "width": 160},
	{"label": "Branch", "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 130},
	{"label": "Admission Date/Time", "fieldname": "admission_datetime", "fieldtype": "Datetime", "width": 160},
	{"label": "Days Admitted", "fieldname": "days_admitted", "fieldtype": "Int", "width": 110},
	{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 120},
	{"label": "Care Level", "fieldname": "care_level", "fieldtype": "Data", "width": 120},
	{"label": "Care Location", "fieldname": "care_location", "fieldtype": "Link", "options": CARE_LOCATION_DOCTYPE, "width": 160},
	{"label": "Attending Veterinarian", "fieldname": "attending_veterinarian", "fieldtype": "Link", "options": "User", "width": 170},
	{"label": "Latest Activity Date/Time", "fieldname": "latest_activity_datetime", "fieldtype": "Datetime", "width": 170},
	{"label": "Pending Charges", "fieldname": "pending_charges", "fieldtype": "Currency", "width": 130},
	{"label": "Invoice Status", "fieldname": "invoice_status", "fieldtype": "Data", "width": 120},
	{"label": "Payment Gate Status", "fieldname": "payment_gate_status", "fieldtype": "Data", "width": 150},
	{"label": "Discharge Readiness Summary", "fieldname": "discharge_readiness_summary", "fieldtype": "Data", "width": 320},
]


def get_active_hospitalisations(filters=None):
	filters = normalize_filters(filters)
	rows = []
	for doc in get_hospitalisation_docs(filters, active_only=True):
		totals = get_charge_totals(doc)
		rows.append({
			"hospitalisation": doc.name,
			"patient": doc.get("patient"),
			"owner": doc.get("customer"),
			"branch": doc.get("service_branch"),
			"admission_datetime": doc.get("admission_datetime"),
			"days_admitted": days_admitted(doc),
			"status": doc.get("status"),
			"care_level": doc.get("care_level"),
			"care_location": doc.get("care_location"),
			"attending_veterinarian": doc.get("attending_veterinarian"),
			"latest_activity_datetime": get_latest_activity_datetime(doc),
			"pending_charges": totals["pending_charges"],
			"invoice_status": doc.get("invoice_status"),
			"payment_gate_status": doc.get("payment_gate_status"),
			"discharge_readiness_summary": get_discharge_readiness_summary(doc),
		})
	return ACTIVE_HOSPITALISATIONS_COLUMNS, rows


CHARGE_SUMMARY_COLUMNS = [
	{"label": "Hospitalisation", "fieldname": "hospitalisation", "fieldtype": "Link", "options": HOSPITALISATION_DOCTYPE, "width": 170},
	{"label": "Patient", "fieldname": "patient", "fieldtype": "Link", "options": "Veterinary Patient", "width": 150},
	{"label": "Pet Owner", "fieldname": "owner", "fieldtype": "Link", "options": "Customer", "width": 150},
	{"label": "Branch", "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 130},
	{"label": "Admission Date", "fieldname": "admission_date", "fieldtype": "Date", "width": 120},
	{"label": "Care Level", "fieldname": "care_level", "fieldtype": "Data", "width": 120},
	{"label": "Total Charges", "fieldname": "total_charges", "fieldtype": "Currency", "width": 130},
	{"label": "Pending Charges", "fieldname": "pending_charges", "fieldtype": "Currency", "width": 130},
	{"label": "Invoiced Charges", "fieldname": "invoiced_charges", "fieldtype": "Currency", "width": 130},
	{"label": "Cancelled Charges", "fieldname": "cancelled_charges", "fieldtype": "Currency", "width": 130},
	{"label": "Missing Price Count", "fieldname": "missing_price_count", "fieldtype": "Int", "width": 130},
	{"label": "Non-Billable Count", "fieldname": "non_billable_count", "fieldtype": "Int", "width": 130},
	{"label": "Linked Invoice / Latest Invoice", "fieldname": "linked_invoice", "fieldtype": "Link", "options": "Sales Invoice", "width": 190},
	{"label": "Invoice Status", "fieldname": "invoice_status", "fieldtype": "Data", "width": 120},
	{"label": "Payment Status", "fieldname": "payment_status", "fieldtype": "Data", "width": 130},
	{"label": "Outstanding", "fieldname": "outstanding_amount", "fieldtype": "Currency", "width": 120},
]


def get_hospitalisation_charge_report(filters=None):
	filters = normalize_filters(filters)
	rows = []
	for doc in get_hospitalisation_docs(filters):
		totals = get_charge_totals(doc)
		if cint(filters.get("missing_price_only")) and not totals["missing_price_count"]:
			continue
		if cint(filters.get("pending_only")) and not totals["pending_charges"]:
			continue
		payment = get_invoice_payment_summary(doc)
		rows.append({
			"hospitalisation": doc.name,
			"patient": doc.get("patient"),
			"owner": doc.get("customer"),
			"branch": doc.get("service_branch"),
			"admission_date": getdate(doc.get("admission_datetime")) if doc.get("admission_datetime") else None,
			"care_level": doc.get("care_level"),
			"total_charges": totals["total_charges"],
			"pending_charges": totals["pending_charges"],
			"invoiced_charges": totals["invoiced_charges"],
			"cancelled_charges": totals["cancelled_charges"],
			"missing_price_count": totals["missing_price_count"],
			"non_billable_count": totals["non_billable_count"],
			"linked_invoice": doc.get("sales_invoice"),
			"invoice_status": doc.get("invoice_status"),
			"payment_status": payment.get("payment_status"),
			"outstanding_amount": payment.get("outstanding_amount"),
		})
	return CHARGE_SUMMARY_COLUMNS, rows


CARE_LOCATION_COLUMNS = [
	{"label": "Care Location", "fieldname": "care_location", "fieldtype": "Link", "options": CARE_LOCATION_DOCTYPE, "width": 170},
	{"label": "Branch", "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 130},
	{"label": "Type", "fieldname": "location_type", "fieldtype": "Data", "width": 100},
	{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 110},
	{"label": "Capacity", "fieldname": "capacity", "fieldtype": "Int", "width": 90},
	{"label": "Active Occupancy", "fieldname": "active_occupancy", "fieldtype": "Int", "width": 130},
	{"label": "Available Slots", "fieldname": "available_slots", "fieldtype": "Int", "width": 120},
	{"label": "Current Patients", "fieldname": "current_patients", "fieldtype": "Data", "width": 220},
	{"label": "Current Hospitalisations", "fieldname": "current_hospitalisations", "fieldtype": "Data", "width": 240},
	{"label": "Assigned Since", "fieldname": "assigned_since", "fieldtype": "Datetime", "width": 160},
	{"label": "Occupancy %", "fieldname": "occupancy_percent", "fieldtype": "Percent", "width": 110},
	{"label": "Usage Indicator", "fieldname": "usage_indicator", "fieldtype": "Data", "width": 120},
]


def get_active_occupancy_by_location() -> dict:
	logs = frappe.get_all(
		CARE_LOCATION_LOG_DOCTYPE,
		filters={"status": "Active"},
		fields=["name", "hospitalisation", "patient", "care_location", "assigned_on"],
	) or []
	by_location = defaultdict(list)
	for log in logs:
		if log.get("hospitalisation") and frappe.db.exists(HOSPITALISATION_DOCTYPE, log.get("hospitalisation")):
			status = frappe.db.get_value(HOSPITALISATION_DOCTYPE, log.get("hospitalisation"), "status")
			if status in {"Discharged", "Cancelled"}:
				continue
		by_location[log.get("care_location")].append(log)
	return by_location


def get_care_location_occupancy_report(filters=None):
	filters = normalize_filters(filters)
	query_filters = {}
	if filters.get("branch"):
		query_filters["branch"] = filters.branch
	if filters.get("location_type"):
		query_filters["location_type"] = filters.location_type
	if filters.get("status"):
		query_filters["status"] = filters.status
	if not cint(filters.get("include_inactive")):
		query_filters["enabled"] = 1
	locations = frappe.get_all(CARE_LOCATION_DOCTYPE, filters=query_filters, fields=["name", "location_name", "branch", "location_type", "status", "capacity", "enabled"], order_by="location_name asc") or []
	occupancy = get_active_occupancy_by_location()
	rows = []
	for location in locations:
		logs = occupancy.get(location.get("name"), [])
		capacity = max(cint(location.get("capacity")) or 1, 1)
		active_count = len(logs)
		if cint(filters.get("occupied_only")) and active_count == 0:
			continue
		assigned_since = min((log.get("assigned_on") for log in logs if log.get("assigned_on")), default=None)
		occupancy_percent = (active_count / capacity) * 100 if capacity else 0
		rows.append({
			"care_location": location.get("name"),
			"branch": location.get("branch"),
			"location_type": location.get("location_type"),
			"status": location.get("status"),
			"capacity": capacity,
			"active_occupancy": active_count,
			"available_slots": max(capacity - active_count, 0),
			"current_patients": ", ".join(filter(None, [log.get("patient") for log in logs])),
			"current_hospitalisations": ", ".join(filter(None, [log.get("hospitalisation") for log in logs])),
			"assigned_since": assigned_since,
			"occupancy_percent": occupancy_percent,
			"usage_indicator": "Full" if active_count >= capacity else ("Occupied" if active_count else "Available"),
		})
	return CARE_LOCATION_COLUMNS, rows


DISCHARGE_WATCH_COLUMNS = [
	{"label": "Hospitalisation", "fieldname": "hospitalisation", "fieldtype": "Link", "options": HOSPITALISATION_DOCTYPE, "width": 170},
	{"label": "Patient", "fieldname": "patient", "fieldtype": "Link", "options": "Veterinary Patient", "width": 150},
	{"label": "Pet Owner", "fieldname": "owner", "fieldtype": "Link", "options": "Customer", "width": 150},
	{"label": "Branch", "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 130},
	{"label": "Admission Date/Time", "fieldname": "admission_datetime", "fieldtype": "Datetime", "width": 160},
	{"label": "Days Admitted", "fieldname": "days_admitted", "fieldtype": "Int", "width": 110},
	{"label": "Care Level", "fieldname": "care_level", "fieldtype": "Data", "width": 120},
	{"label": "Care Location", "fieldname": "care_location", "fieldtype": "Link", "options": CARE_LOCATION_DOCTYPE, "width": 160},
	{"label": "Attending Veterinarian", "fieldname": "attending_veterinarian", "fieldtype": "Link", "options": "User", "width": 170},
	{"label": "Discharge Readiness", "fieldname": "discharge_readiness", "fieldtype": "Data", "width": 260},
	{"label": "Pending Charges", "fieldname": "pending_charges", "fieldtype": "Currency", "width": 130},
	{"label": "Missing Prices", "fieldname": "missing_prices", "fieldtype": "Int", "width": 110},
	{"label": "Pending Stock Posting", "fieldname": "pending_stock_posting", "fieldtype": "Int", "width": 150},
	{"label": "Care Location Assigned?", "fieldname": "care_location_assigned", "fieldtype": "Data", "width": 150},
	{"label": "Follow-up Date", "fieldname": "follow_up_date", "fieldtype": "Date", "width": 120},
	{"label": "Notes / Warning Summary", "fieldname": "warning_summary", "fieldtype": "Data", "width": 320},
]


def get_discharge_watch_report(filters=None):
	filters = normalize_filters(filters)
	rows = []
	minimum_days = cint(filters.get("minimum_days_admitted")) if filters.get("minimum_days_admitted") not in (None, "") else 3
	pending_issue_type = filters.get("pending_issue_type")
	for doc in get_hospitalisation_docs(filters, active_only=True):
		days = days_admitted(doc)
		if days < minimum_days:
			continue
		totals = get_charge_totals(doc)
		pending_stock = get_pending_stock_count(doc)
		readiness = build_hospitalisation_discharge_readiness(doc)
		messages = readiness.get("messages") or readiness.get("warnings") or []
		if cint(filters.get("discharge_ready_only")) and not readiness.get("can_discharge"):
			continue
		if pending_issue_type and not pending_issue_matches(pending_issue_type, doc, totals, pending_stock, messages):
			continue
		rows.append({
			"hospitalisation": doc.name,
			"patient": doc.get("patient"),
			"owner": doc.get("customer"),
			"branch": doc.get("service_branch"),
			"admission_datetime": doc.get("admission_datetime"),
			"days_admitted": days,
			"care_level": doc.get("care_level"),
			"care_location": doc.get("care_location"),
			"attending_veterinarian": doc.get("attending_veterinarian"),
			"discharge_readiness": "Ready" if readiness.get("can_discharge") else "Needs Attention",
			"pending_charges": totals["pending_charges"],
			"missing_prices": totals["missing_price_count"],
			"pending_stock_posting": pending_stock,
			"care_location_assigned": "Yes" if doc.get("care_location") else "No",
			"follow_up_date": doc.get("follow_up_date"),
			"warning_summary": "; ".join(messages),
		})
	return DISCHARGE_WATCH_COLUMNS, rows


def pending_issue_matches(issue_type: str, doc, totals: dict, pending_stock: int, messages: list[str]) -> bool:
	if issue_type == "Missing Price Charges":
		return totals["missing_price_count"] > 0
	if issue_type == "Pending Charge Sync":
		return totals["pending_charges"] > 0
	if issue_type == "Pending Stock Posting":
		return pending_stock > 0
	if issue_type == "Care Location Still Assigned":
		return bool(doc.get("care_location"))
	if issue_type == "Pending Discharge Summary":
		return not bool(doc.get("discharge_summary"))
	return any(issue_type.lower() in message.lower() for message in messages)


PENDING_ACTION_COLUMNS = [
	{"label": "Action Type", "fieldname": "action_type", "fieldtype": "Data", "width": 180},
	{"label": "Priority", "fieldname": "priority", "fieldtype": "Data", "width": 90},
	{"label": "Hospitalisation", "fieldname": "hospitalisation", "fieldtype": "Link", "options": HOSPITALISATION_DOCTYPE, "width": 170},
	{"label": "Patient", "fieldname": "patient", "fieldtype": "Link", "options": "Veterinary Patient", "width": 150},
	{"label": "Owner", "fieldname": "owner", "fieldtype": "Link", "options": "Customer", "width": 150},
	{"label": "Branch", "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 130},
	{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 120},
	{"label": "Care Level", "fieldname": "care_level", "fieldtype": "Data", "width": 120},
	{"label": "Care Location", "fieldname": "care_location", "fieldtype": "Link", "options": CARE_LOCATION_DOCTYPE, "width": 160},
	{"label": "Last Activity", "fieldname": "last_activity", "fieldtype": "Datetime", "width": 160},
	{"label": "Amount Impact", "fieldname": "amount_impact", "fieldtype": "Currency", "width": 130},
	{"label": "Suggested Action", "fieldname": "suggested_action", "fieldtype": "Data", "width": 260},
]


def get_pending_hospitalisation_actions(filters=None):
	filters = normalize_filters(filters)
	rows = []
	for doc in get_hospitalisation_docs(filters, active_only=True):
		actions = get_pending_actions_for_doc(doc)
		for action in actions:
			if filters.get("action_type") and action["action_type"] != filters.action_type:
				continue
			rows.append({
				**action,
				"hospitalisation": doc.name,
				"patient": doc.get("patient"),
				"owner": doc.get("customer"),
				"branch": doc.get("service_branch"),
				"status": doc.get("status"),
				"care_level": doc.get("care_level"),
				"care_location": doc.get("care_location"),
				"last_activity": get_latest_activity_datetime(doc),
			})
	return PENDING_ACTION_COLUMNS, rows


def get_pending_actions_for_doc(doc) -> list[dict]:
	totals = get_charge_totals(doc)
	pending_stock = get_pending_stock_count(doc)
	actions = []
	if totals["missing_price_count"]:
		actions.append({"action_type": "Missing Price Charges", "priority": "High", "amount_impact": totals["missing_price_amount"], "suggested_action": "Enter charge item rates before invoice sync."})
	if totals["pending_charges"]:
		actions.append({"action_type": "Pending Charge Sync", "priority": "Medium", "amount_impact": totals["pending_charges"], "suggested_action": "Sync charges to invoice."})
	if pending_stock:
		actions.append({"action_type": "Pending Stock Posting", "priority": "Medium", "amount_impact": 0, "suggested_action": "Review and post stock usage."})
	if doc.get("care_location"):
		actions.append({"action_type": "Care Location Still Assigned", "priority": "Low", "amount_impact": 0, "suggested_action": "Release care location when patient leaves."})
	if not doc.get("discharge_summary") and doc.get("status") == "Ready for Discharge":
		actions.append({"action_type": "Pending Discharge Summary", "priority": "High", "amount_impact": 0, "suggested_action": "Complete discharge summary."})
	if not get_latest_activity_datetime(doc):
		actions.append({"action_type": "No Recent Activity", "priority": "Low", "amount_impact": 0, "suggested_action": "Record a clinical activity update."})
	if should_flag_pending_daily_charges(doc):
		actions.append({"action_type": "Pending Daily Charges", "priority": "Medium", "amount_impact": 0, "suggested_action": "Generate daily stay charges."})
	return actions


def should_flag_pending_daily_charges(doc) -> bool:
	if doc.get("status") not in ACTIVE_STATUSES:
		return False
	daily_dates = {getdate(row.get("charge_date")) for row in doc.get("charge_items") or [] if row.get("charge_category") == "Daily Stay" and row.get("billing_status") != "Cancelled" and row.get("charge_date")}
	admission = doc.get("admission_datetime")
	if not admission:
		return False
	return getdate(admission) not in daily_dates
