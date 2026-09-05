from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from vetedge.services.report_export import (
	MAX_CURRENT_PAGE_LENGTH,
	_column_dict,
	_csv_bytes,
	_json_dict,
	_normalize_options,
	_pdf_bytes,
	_pdf_html,
	_select_columns,
	_set_download_response,
	_table_matrix,
	_xlsx_bytes,
)
from vetedge.services.reporting_capabilities import require_reporting_action
from vetedge.services.stock_expiry_interactive import get_stock_expiry_interactive_data
from vetedge.services.stock_expiry_monitor import (
	get_report_columns,
	get_status_chart,
	get_stock_expiry_rows,
	get_summary,
)
from vetedge.veterinary.page.stock_expiry_monitor.stock_expiry_monitor import (
	_normalize_stock_expiry_filters,
	_validate_reference_filter,
	check_expiry_permissions,
)

SCOPE_NAME = "Stock Expiry Status"
REPORT_TITLE = "Stock Expiry Monitor"
MAX_SYNC_ALL_FILTERED_ROWS = 20000


def _normalized_filters(filters: str | dict | None) -> dict:
	value = _normalize_stock_expiry_filters(_json_dict(filters))
	value.pop("limit", None)
	value.pop("offset", None)
	threshold = value.get("days_threshold")
	if threshold:
		value["expiry_buckets"] = str(threshold)
	_validate_reference_filter(value, "warehouse")
	_validate_reference_filter(value, "item_group")
	return value


def _apply_window(rows: list[dict], filters: dict) -> list[dict]:
	window = str(filters.get("expiry_window") or "all").strip().lower()
	if window == "expired":
		return [row for row in rows if row.get("expiry_status") == "Expired"]
	if window == "expiring soon":
		return [row for row in rows if row.get("expiry_status") == "Expiring Soon"]
	return rows


def _summary_from_aggregate(summary: dict) -> list[dict]:
	return [
		{"label": _("Total Items"), "value": cint(summary.get("total_items")), "indicator": "Blue", "datatype": "Int"},
		{"label": _("Expired"), "value": cint(summary.get("expired_items")), "indicator": "Red", "datatype": "Int"},
		{"label": _("Expiring Soon"), "value": cint(summary.get("expiring_soon")), "indicator": "Orange", "datatype": "Int"},
		{"label": _("Safe"), "value": cint(summary.get("safe_items")), "indicator": "Green", "datatype": "Int"},
	]


def _document_model(filters: str | dict | None, options: str | dict | None, start: int, page_length: int):
	filters_dict = _normalized_filters(filters)
	export_options = _normalize_options(options)
	all_columns = [_column_dict(column, index) for index, column in enumerate(get_report_columns())]
	columns = _select_columns(all_columns, export_options["columns"])
	if not columns:
		frappe.throw(_("No Stock Expiry columns are available for this action."))

	window = filters_dict.get("expiry_window") or "all"
	if export_options["scope"] == "current_page":
		start = max(0, cint(start))
		page_length = min(MAX_CURRENT_PAGE_LENGTH, max(1, cint(page_length) or 50))
		interactive = get_stock_expiry_interactive_data(
			filters_dict,
			expiry_window=window,
			limit=page_length,
			offset=start,
		)
		rows = interactive.get("rows") or []
		summary = _summary_from_aggregate(interactive.get("summary") or {})
		chart = get_status_chart(summary)
		return filters_dict, export_options, columns, rows, summary, chart

	# Protect the synchronous web worker before materialising a complete export.
	# A future queued exporter can raise/remove this cap without changing the
	# interactive report contract.
	guard = get_stock_expiry_interactive_data(filters_dict, expiry_window=window, limit=1, offset=0)
	matching_rows = cint(guard.get("total_count"))
	if matching_rows > MAX_SYNC_ALL_FILTERED_ROWS:
		frappe.throw(
			_("This export contains {0} rows, which exceeds the synchronous export limit of {1}. Narrow the filters before exporting all records.").format(
				matching_rows, MAX_SYNC_ALL_FILTERED_ROWS
			),
			frappe.ValidationError,
			title=_("Export Too Large"),
		)

	source_rows = get_stock_expiry_rows(filters_dict)
	rows = _apply_window(source_rows, filters_dict)
	summary = get_summary(source_rows)
	chart = get_status_chart(summary)
	return filters_dict, export_options, columns, rows, summary, chart


@frappe.whitelist()
@frappe.read_only()
def download_stock_expiry_export(
	filters: str | dict | None = None,
	options: str | dict | None = None,
	start: int = 0,
	page_length: int = 50,
) -> None:
	"""Export Stock Expiry from the same permission-aware dataset as the monitor."""
	check_expiry_permissions()
	require_reporting_action(SCOPE_NAME, scope_type="report", action="export")
	filters_dict, export_options, columns, rows, summary, chart = _document_model(
		filters, options, start, page_length
	)
	file_format = export_options["format"]

	if file_format == "pdf":
		content = _pdf_bytes(
			_pdf_html(REPORT_TITLE, filters_dict, columns, rows, summary, export_options, chart=chart),
			export_options["orientation"],
		)
	elif file_format == "csv":
		matrix, _ = _table_matrix(
			REPORT_TITLE, filters_dict, columns, rows, summary, export_options, chart=chart
		)
		content = _csv_bytes(matrix)
	else:
		matrix, header_index = _table_matrix(
			REPORT_TITLE, filters_dict, columns, rows, summary, export_options, chart=chart
		)
		content = _xlsx_bytes(
			matrix, REPORT_TITLE, header_index, export_options["include_filters"]
		)

	_set_download_response(content, "Stock-Expiry-Monitor", file_format)


@frappe.whitelist()
@frappe.read_only()
def get_stock_expiry_print_html(
	filters: str | dict | None = None,
	options: str | dict | None = None,
	start: int = 0,
	page_length: int = 50,
) -> str:
	"""Return printable Stock Expiry HTML using the same document model as PDF export."""
	check_expiry_permissions()
	require_reporting_action(SCOPE_NAME, scope_type="report", action="print")
	filters_dict, export_options, columns, rows, summary, chart = _document_model(
		filters, options, start, page_length
	)
	return _pdf_html(
		REPORT_TITLE,
		filters_dict,
		columns,
		rows,
		summary,
		export_options,
		chart=chart,
	)
