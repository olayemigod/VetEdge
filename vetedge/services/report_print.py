from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from vetedge.services.report_export import (
	MAX_CURRENT_PAGE_LENGTH,
	_column_dict,
	_json_dict,
	_normalize_options,
	_normalize_rows,
	_pdf_html,
	_run_report,
	_select_columns,
)


@frappe.whitelist()
@frappe.read_only()
def get_report_print_html(
	report_name: str,
	filters: str | dict | None = None,
	options: str | dict | None = None,
	start: int = 0,
	page_length: int = 50,
) -> str:
	"""Return the same paginated document model used for PDF, for explicit browser Print."""
	if not report_name:
		frappe.throw(_("Report name is required."))

	filters_dict = _json_dict(filters)
	print_options = _normalize_options(options)
	payload = _run_report(report_name, filters_dict)
	all_columns = [_column_dict(column, index) for index, column in enumerate(payload.get("columns") or [])]
	rows = _normalize_rows(payload.get("result") or [], all_columns)
	columns = _select_columns(all_columns, print_options["columns"])
	if not columns:
		frappe.throw(_("No report columns are available for printing."))

	if print_options["scope"] == "current_page":
		start = max(0, cint(start))
		page_length = min(MAX_CURRENT_PAGE_LENGTH, max(1, cint(page_length) or 50))
		rows = rows[start : start + page_length]

	return _pdf_html(
		report_name,
		filters_dict,
		columns,
		rows,
		payload.get("report_summary") or [],
		print_options,
	)
