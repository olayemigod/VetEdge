from __future__ import annotations

from copy import deepcopy

import frappe
from frappe.utils import cstr

from vetedge.services.stock import get_branch_dispensary_warehouse

UNMAPPED_BRANCH_WAREHOUSE = "__VETEDGE_UNMAPPED_BRANCH_WAREHOUSE__"


def normalize_stock_expiry_branch_scope(filters=None) -> dict:
	"""Fail closed when Stock Expiry is scoped to a Branch.

	A valid Branch without a configured dispensary Warehouse must never cause the
	Warehouse predicate to disappear. Likewise an explicitly supplied Warehouse
	must agree with the Branch mapping. The impossible sentinel deliberately
	produces an empty dataset without revealing stock from another branch.
	"""
	filters = frappe._dict(deepcopy(dict(filters or {})))
	branch = cstr(filters.get("branch") or "").strip()
	if not branch:
		return dict(filters)

	company = cstr(filters.get("company") or "").strip() or None
	mapped_warehouse = get_branch_dispensary_warehouse(branch, company, required=False)
	requested_warehouse = cstr(filters.get("warehouse") or "").strip()

	if not mapped_warehouse:
		filters["warehouse"] = UNMAPPED_BRANCH_WAREHOUSE
	elif requested_warehouse and requested_warehouse != mapped_warehouse:
		filters["warehouse"] = UNMAPPED_BRANCH_WAREHOUSE
	else:
		filters["warehouse"] = mapped_warehouse

	return dict(filters)
