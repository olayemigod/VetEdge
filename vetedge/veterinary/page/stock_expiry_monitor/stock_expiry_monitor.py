# -*- coding: utf-8 -*-
# Copyright (c) 2026, ProcessEdge Solutions and contributors
# For license information, please see license.txt

import datetime

import frappe
from frappe.utils import cint

from vetedge.services.report_visibility import normalize_report_filters
from vetedge.services.reporting_catalog import require_reporting_entitlement
from vetedge.services.stock import get_branch_dispensary_warehouse
from vetedge.services.stock_expiry_scope import (
	UNMAPPED_BRANCH_WAREHOUSE,
	normalize_stock_expiry_branch_scope,
)

FILTER_SEARCH_MAX_PAGE_LENGTH = 20
FILTER_SEARCH_CONFIG = {
	"warehouse": {"doctype": "Warehouse", "filters": {"is_group": 0}},
	"item_group": {"doctype": "Item Group", "filters": {}},
}


@frappe.whitelist()
def search_stock_expiry_filter_options(field: str, txt: str = "", start: int = 0, page_length: int = 20):
	"""Return a small permission- and branch-aware search window for Stock Expiry filters."""
	check_expiry_permissions()
	require_reporting_entitlement("Stock Expiry Status", scope_type="report")
	config = FILTER_SEARCH_CONFIG.get(str(field or "").strip())
	if not config:
		frappe.throw("This Stock Expiry filter is not searchable.", frappe.PermissionError)

	doctype = config["doctype"]
	if not frappe.has_permission(doctype, "read"):
		return []

	filters = dict(config["filters"])
	if field == "warehouse":
		scope = _normalize_stock_expiry_filters({})
		branch = str(scope.get("branch") or "").strip()
		if branch:
			warehouse = get_branch_dispensary_warehouse(branch, scope.get("company"), required=False)
			if not warehouse:
				return []
			filters["name"] = warehouse

	query = str(txt or "").strip()
	if query:
		if field == "warehouse" and filters.get("name"):
			if query.lower() not in str(filters["name"]).lower():
				return []
		else:
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


def _normalize_stock_expiry_filters(filters=None) -> dict:
	parsed = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	if not isinstance(parsed, dict):
		frappe.throw("Expected Stock Expiry filters as a JSON object.", frappe.ValidationError)
	cleaned = {key: value for key, value in parsed.items() if value not in (None, "")}
	normalized = dict(normalize_report_filters("Stock Expiry Status", cleaned) or {})
	return normalize_stock_expiry_branch_scope(normalized)


def _validate_reference_filter(filters: dict, field: str) -> None:
	value = str(filters.get(field) or "").strip()
	if not value:
		return
	if field == "warehouse" and value == UNMAPPED_BRANCH_WAREHOUSE:
		return

	config = FILTER_SEARCH_CONFIG[field]
	if field == "warehouse":
		branch = str(filters.get("branch") or "").strip()
		if branch:
			branch_warehouse = get_branch_dispensary_warehouse(branch, filters.get("company"), required=False)
			if not branch_warehouse or value != branch_warehouse:
				frappe.throw(
					"The selected warehouse is not valid for the active branch context.",
					frappe.PermissionError,
				)

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
	require_reporting_entitlement("Stock Expiry Status", scope_type="report")
	filters = _normalize_stock_expiry_filters(filters)

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
