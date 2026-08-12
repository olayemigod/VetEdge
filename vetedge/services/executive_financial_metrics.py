from __future__ import annotations

import frappe
from frappe.utils import cint, cstr, date_diff, flt, getdate, nowdate


def count_executive_unpaid_invoices(filters=None) -> int:
	"""Count Executive unpaid invoices without materialising report-only presentation rows."""
	filters = frappe._dict(filters or {})

	from vetedge.services.reporting_structure import (
		_build_invoice_context_map,
		_get_sales_invoice_rows,
		_resolve_invoice_report_branch,
	)

	docstatus_value = filters.get("docstatus")
	draft_mode = filters.get("status") == "Draft" or docstatus_value in (0, "0")
	invoices = _get_sales_invoice_rows(filters, unpaid_only=not draft_mode)
	if draft_mode:
		invoices = [row for row in invoices if cint(row.get("docstatus")) == 0]
	else:
		invoices = [
			row
			for row in invoices
			if cint(row.get("docstatus")) == 1 and flt(row.get("outstanding_amount")) > 0
		]

	age_range = cstr(filters.get("age_range") or "").strip()
	if age_range:
		invoices = [row for row in invoices if _matches_age_range(row, age_range)]

	branch = cstr(filters.get("branch") or "").strip()
	if not branch or not invoices:
		return len(invoices)

	invoice_names = [row.get("name") for row in invoices if row.get("name")]
	context_map = _build_invoice_context_map(invoice_names)
	return sum(
		1
		for row in invoices
		if _resolve_invoice_report_branch(row, context_map.get(row.get("name"), {})) == branch
	)


def _matches_age_range(invoice, age_range: str) -> bool:
	age_base = getdate(invoice.get("due_date") or invoice.get("posting_date") or nowdate())
	age_days = max(0, date_diff(nowdate(), age_base))
	if age_range == "0-30":
		return 0 <= age_days <= 30
	if age_range == "31-60":
		return 31 <= age_days <= 60
	if age_range == "61-90":
		return 61 <= age_days <= 90
	if age_range == "90+":
		return age_days >= 91
	return True
