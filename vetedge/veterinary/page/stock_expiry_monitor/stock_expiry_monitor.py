# -*- coding: utf-8 -*-
# Copyright (c) 2026, ProcessEdge Solutions and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, nowdate, flt
import datetime

@frappe.whitelist()
def get_stock_expiry_data(filters=None):
	"""Fetches filtered and paginated stock expiry rows, along with overall summaries."""
	# Assert user permissions
	check_expiry_permissions()

	# Parse filters
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	
	# Coerce dates and settings
	today = filters.get("posting_date") or nowdate()
	
	# Configure threshold days for the core service
	threshold = filters.get("days_threshold")
	if threshold:
		filters["expiry_buckets"] = str(threshold)

	from vetedge.services.stock_expiry_monitor import get_stock_expiry_rows

	# Get full filtered dataset from existing VetEdge stock expiry service
	all_rows = get_stock_expiry_rows(filters)

	# Calculate summary cards from the full filtered dataset (before table-specific window filter & pagination)
	expired_rows = [r for r in all_rows if r.get("expiry_status") == "Expired"]
	expiring_soon_rows = [r for r in all_rows if r.get("expiry_status") == "Expiring Soon"]
	affected_rows = [r for r in all_rows if r.get("expiry_status") in ("Expired", "Expiring Soon")]

	expired_count = len(expired_rows)
	expiring_soon_count = len(expiring_soon_rows)
	total_qty = sum(flt(r.get("qty")) for r in affected_rows)
	unique_warehouses = len({r.get("warehouse") for r in affected_rows if r.get("warehouse")})
	highest_risk_items = len({r.get("item_code") for r in expired_rows if r.get("item_code")})
	last_updated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

	summary = {
		"expired_items": expired_count,
		"expiring_soon": expiring_soon_count,
		"affected_qty": total_qty,
		"affected_warehouses": unique_warehouses,
		"highest_risk_items": highest_risk_items,
		"last_updated": last_updated
	}

	# Apply table-specific window filter (expired, expiring soon, all)
	window = filters.get("expiry_window") or "all"
	table_rows = []
	for r in all_rows:
		status = r.get("expiry_status")
		if window == "expired" and status != "Expired":
			continue
		if window == "expiring soon" and status != "Expiring Soon":
			continue
		table_rows.append(r)

	# Paginate table rows
	limit = min(int(filters.get("limit") or 50), 500)
	offset = int(filters.get("offset") or 0)
	paginated_rows = table_rows[offset:offset + limit]

	return {
		"summary": summary,
		"rows": paginated_rows,
		"total_count": len(table_rows),
		"limit": limit,
		"offset": offset
	}

def check_expiry_permissions():
	"""Validate that the active user possesses stock manager or veterinary administrative roles."""
	roles = {
		"System Manager", 
		"VetEdge Administrator", 
		"Dispensary User", 
		"VetEdge Dispensary User", 
		"Branch Manager", 
		"VetEdge Branch Manager"
	}
	user_roles = set(frappe.get_roles(frappe.session.user))
	if not user_roles.intersection(roles):
		frappe.throw("You do not have permission to access the Stock Expiry Monitor.", frappe.PermissionError)
