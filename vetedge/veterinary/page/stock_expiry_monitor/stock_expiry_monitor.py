# -*- coding: utf-8 -*-
# Copyright (c) 2026, ProcessEdge Solutions and contributors
# For license information, please see license.txt

import datetime

import frappe
from frappe.utils import cint

FILTER_SEARCH_MAX_PAGE_LENGTH = 20
FILTER_SEARCH_CONFIG = {
	"warehouse": {"doctype": "Warehouse", "filters": {"is_group": 0}},
	"item_group": {"doctype": "Item Group", "filters": {}},
}


@frappe.whitelist()
def search_stock_expiry_filter_options(field: str, txt: str = "", start: int = 0, page_length: int = 20):
	"""Return a small permission-aware search window for Stock Expiry filters."""
	check_expiry_permissions()
	config = FILTER_SEARCH_CONFIG.get(str(field or "").strip())
	if not config:
		frappe.throw("This Stock Expiry filter is not searchable.", frappe.PermissionError)

	doctype = config["doctype"]
	if not frappe.has_permission(doctype, "read"):
		return []

	filters = dict(config["filters"])
	query = str(txt or "").strip()
	if query:
		filters["name"] = ["like", f"%{query}%"]

	start = max(cint(start), 0)
	page_length = min(max(cint(page_length) or FILTER_SEARCH_MAX_PAGE_LENGTH, 1), FILTER_SEARCH_MAX_PAGE_LENGTH)
	rows = frappe.get_list(
		doctype,
		fields=["name"],
		filters=filters,
		order_by="name asc",
		start=start,
		page_length=page_length,
	)
	return [{"value": row.name, "label": row.name} for row in rows]


def _validate_reference_filter(filters: dict, field: str) -> None:
	value = str(filters.get(field) or "").strip()
	if not value:
		return

	config = FILTER_SEARCH_CONFIG[field]
	exact_filters = dict(config["filters"])
	exact_filters["name"] = value
	rows = frappe.get_list(
		config["doctype"],
		fields=["name"],
		filters=exact_filters,
		page_length=1,
	)
	if not rows:
		frappe.throw(
			f"The selected {field.replace('_', ' ')} is not available to this user.",
			frappe.PermissionError,
		)


@frappe.whitelist()
def get_stock_expiry_data(filters=None):
	"""Fetch Stock Expiry summary plus one server-paginated interactive window."""
	check_expiry_permissions()
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})

	_validate_reference_filter(filters, "warehouse")
	_validate_reference_filter(filters, "item_group")

	threshold = filters.get("days_threshold")
	if threshold:
		filters["expiry_buckets"] = str(threshold)

	from vetedge.services.stock_expiry_interactive import get_stock_expiry_interactive_data

	result = get_stock_expiry_interactive_data(
		filters,
		expiry_window=filters.get("expiry_window") or "all",
		limit=min(max(cint(filters.get("limit")) or 50, 1), 500),
		offset=max(cint(filters.get("offset")), 0),
	)
	result["summary"]["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
	return result


def check_expiry_permissions():
	"""Validate that the active user possesses Stock Expiry Monitor access roles."""
	roles = {
		"System Manager",
		"VetEdge Administrator",
		"Dispensary User",
		"VetEdge Dispensary User",
		"Branch Manager",
		"VetEdge Branch Manager",
	}
	user_roles = set(frappe.get_roles(frappe.session.user))
	if not user_roles.intersection(roles):
		frappe.throw("You do not have permission to access the Stock Expiry Monitor.", frappe.PermissionError)
