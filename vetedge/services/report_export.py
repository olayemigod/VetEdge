from __future__ import annotations

import csv
import html
import io
import json
from datetime import datetime
from typing import Any

import frappe
from frappe import _
from frappe.desk.query_report import run as run_query_report
from frappe.utils import cint
from frappe.utils.pdf import get_chrome_pdf, get_pdf
from frappe.utils.xlsxutils import make_xlsx


MIME_TYPES = {
	"xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
	"csv": "text/csv; charset=utf-8",
	"pdf": "application/pdf",
}
PRESENTATION_KEYS = (
	"include_summary",
	"include_filters",
	"include_charts",
	"include_letterhead",
	"include_title",
	"include_generated_metadata",
	"include_totals",
)
MAX_CURRENT_PAGE_LENGTH = 200


def _json_dict(value: str | dict | None) -> dict:
	if not value:
		return {}
	if isinstance(value, dict):
		return dict(value)
	parsed = json.loads(value)
	if not isinstance(parsed, dict):
		frappe.throw(_("Report export options must be a JSON object."))
	return parsed


def _normalize_options(options: str | dict | None) -> dict:
	value = _json_dict(options)
	file_format = str(value.get("format") or "xlsx").lower()
	if file_format not in MIME_TYPES:
		frappe.throw(_("Unsupported report export format."))
	scope = str(value.get("scope") or "all_filtered")
	if scope not in {"current_page", "all_filtered"}:
		frappe.throw(_("Unsupported report export scope."))
	normalized = {
		"format": file_format,
		"scope": scope,
		"columns": [str(item) for item in (value.get("columns") or []) if item],
		"orientation": str(value.get("orientation") or "auto").lower(),
		"repeat_table_headings": value.get("repeat_table_headings") is not False,
	}
	for key in PRESENTATION_KEYS:
		normalized[key] = bool(value.get(key))
	normalized["raw_table_only"] = not any(normalized[key] for key in PRESENTATION_KEYS)
	return normalized


def _column_dict(column: Any, index: int) -> dict:
	if isinstance(column, dict):
		return {
			**column,
			"label": column.get("label") or column.get("fieldname") or f"Column {index + 1}",
			"fieldname": column.get("fieldname") or column.get("key") or f"column_{index + 1}",
		}
	if isinstance(column, str):
		parts = column.split(":")
		return {
			"label": parts[0] if parts else f"Column {index + 1}",
			"fieldname": parts[1] if len(parts) > 1 and parts[1] else f"column_{index + 1}",
			"fieldtype": parts[2] if len(parts) > 2 else "Data",
		}
	return {"label": f"Column {index + 1}", "fieldname": f"column_{index + 1}", "fieldtype": "Data"}


def _normalize_rows(rows: list, columns: list[dict]) -> list[dict]:
	output = []
	for row in rows or []:
		if isinstance(row, dict):
			output.append(row)
		else:
			output.append({column["fieldname"]: row[index] if index < len(row) else None for index, column in enumerate(columns)})
	return output


def _run_report(report_name: str, filters: dict) -> dict:
	# Frappe run() validates Report/ref_doctype permissions and filters before execution.
	return run_query_report(
		report_name=report_name,
		filters=filters,
		ignore_prepared_report=True,
		are_default_filters=False,
	) or {}


def _select_columns(columns: list[dict], selected: list[str]) -> list[dict]:
	if not selected:
		return [column for column in columns if not column.get("hidden")]
	by_fieldname = {column.get("fieldname"): column for column in columns if column.get("fieldname")}
	return [by_fieldname[fieldname] for fieldname in selected if fieldname in by_fieldname]


def _slice_rows(rows: list[dict], options: dict, start: int, page_length: int) -> list[dict]:
	if options["scope"] != "current_page":
		return rows
	start = max(0, cint(start))
	page_length = min(MAX_CURRENT_PAGE_LENGTH, max(1, cint(page_length) or 50))
	return rows[start : start + page_length]


def _safe_value(value: Any) -> Any:
	if value is None:
		return ""
	if isinstance(value, (str, int, float, bool, datetime)):
		return value
	return str(value)


def _summary_rows(summary: list | None) -> list[list[Any]]:
	rows = []
	for item in summary or []:
		if not isinstance(item, dict):
			continue
		rows.append([item.get("label") or item.get("fieldname") or _("Metric"), _safe_value(item.get("value"))])
	return rows


def _filter_rows(filters: dict) -> list[list[Any]]:
	return [[str(key).replace("_", " ").title(), _safe_value(value)] for key, value in filters.items() if value not in (None, "", [])]


def _default_letterhead_html() -> str:
	company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
	letterhead_name = frappe.get_cached_value("Company", company, "default_letter_head") if company else None
	if not letterhead_name:
		matches = frappe.get_all("Letter Head", filters={"is_default": 1, "disabled": 0}, pluck="name", limit=1)
		letterhead_name = matches[0] if matches else None
	if not letterhead_name:
		return ""
	letterhead = frappe.get_doc("Letter Head", letterhead_name)
	if not letterhead.has_permission("read"):
		return ""
	return letterhead.content or ""


def _table_matrix(report_name: str, filters: dict, columns: list[dict], rows: list[dict], summary: list, options: dict) -> tuple[list[list[Any]], int]:
	matrix: list[list[Any]] = []
	if options["include_title"]:
		matrix.append([report_name])
	if options["include_generated_metadata"]:
		matrix.append([_("Generated"), frappe.utils.now_datetime().isoformat(sep=" ", timespec="seconds")])
		matrix.append([_("Generated By"), frappe.session.user])
	if options["include_filters"]:
		matrix.extend(_filter_rows(filters))
	if options["include_summary"]:
		matrix.extend(_summary_rows(summary))
	if matrix:
		matrix.append([])
	header_index = len(matrix)
	matrix.append([column.get("label") or column["fieldname"] for column in columns])
	for row in rows:
		matrix.append([_safe_value(row.get(column["fieldname"])) for column in columns])
	return matrix, header_index


def _csv_bytes(matrix: list[list[Any]]) -> bytes:
	stream = io.StringIO(newline="")
	writer = csv.writer(stream)
	for row in matrix:
		writer.writerow([_safe_value(value) for value in row])
	return stream.getvalue().encode("utf-8-sig")


def _xlsx_bytes(matrix: list[list[Any]], report_name: str, header_index: int, include_filters: bool) -> bytes:
	stream = make_xlsx(matrix, report_name[:31] or "Report", header_index=header_index, has_filters=include_filters)
	return stream.getvalue()


def _pdf_html(report_name: str, filters: dict, columns: list[dict], rows: list[dict], summary: list, options: dict) -> str:
	parts = ["<!doctype html><html><head><meta charset='utf-8'><style>"]
	parts.append("@page{margin:12mm}body{font-family:Arial,sans-serif;color:#172033;font-size:9pt}h1{font-size:16pt;margin:0 0 8px}.meta,.filters,.summary{margin:0 0 10px}.summary{display:flex;gap:8px;flex-wrap:wrap}.card{border:1px solid #dfe5ef;border-radius:6px;padding:6px 9px}.card b{display:block;font-size:11pt}table{width:100%;border-collapse:collapse}th,td{border:1px solid #dfe5ef;padding:5px;vertical-align:top}th{background:#f3f5f8;text-align:left}")
	if options["repeat_table_headings"]:
		parts.append("thead{display:table-header-group}")
	parts.append("</style></head><body>")
	if options["include_letterhead"]:
		parts.append(_default_letterhead_html())
	if options["include_title"]:
		parts.append(f"<h1>{html.escape(report_name)}</h1>")
	if options["include_generated_metadata"]:
		parts.append(f"<div class='meta'>{html.escape(_('Generated'))}: {html.escape(str(frappe.utils.now_datetime()))} · {html.escape(frappe.session.user)}</div>")
	if options["include_filters"]:
		filter_text = " · ".join(f"{html.escape(str(key).replace('_', ' ').title())}: {html.escape(str(value))}" for key, value in filters.items() if value not in (None, "", []))
		if filter_text:
			parts.append(f"<div class='filters'>{filter_text}</div>")
	if options["include_summary"] and summary:
		parts.append("<div class='summary'>")
		for item in summary:
			if isinstance(item, dict):
				parts.append(f"<div class='card'>{html.escape(str(item.get('label') or _('Metric')))}<b>{html.escape(str(item.get('value') or 0))}</b></div>")
		parts.append("</div>")
	parts.append("<table><thead><tr>")
	for column in columns:
		parts.append(f"<th>{html.escape(str(column.get('label') or column['fieldname']))}</th>")
	parts.append("</tr></thead><tbody>")
	for row in rows:
		parts.append("<tr>")
		for column in columns:
			parts.append(f"<td>{html.escape(str(_safe_value(row.get(column['fieldname']))))}</td>")
		parts.append("</tr>")
	parts.append("</tbody></table></body></html>")
	return "".join(parts)


def _pdf_bytes(content: str, orientation: str) -> bytes:
	pdf_orientation = "Landscape" if orientation == "landscape" else "Portrait" if orientation == "portrait" else "Landscape"
	options = {"orientation": pdf_orientation}
	try:
		generated = get_chrome_pdf(print_format=None, html=content, options=options.copy(), output=None, pdf_generator="chrome")
		if generated:
			return generated
	except Exception:
		frappe.log_error(title="VetEdge Report Export Chrome PDF Failed", message=frappe.get_traceback())
	return get_pdf(content, options=options)


def _set_download_response(content: bytes, filename: str, file_format: str) -> None:
	if not content:
		frappe.throw(_("The generated report export is empty."))
	frappe.local.response.filename = f"{filename}.{file_format}"
	frappe.local.response.filecontent = content
	frappe.local.response.type = "download"
	frappe.local.response.content_type = MIME_TYPES[file_format]
	frappe.local.response.display_content_as = "attachment"


@frappe.whitelist()
@frappe.read_only()
def download_report_export(
	report_name: str,
	filters: str | dict | None = None,
	options: str | dict | None = None,
	start: int = 0,
	page_length: int = 50,
) -> None:
	if not report_name:
		frappe.throw(_("Report name is required."))
	filters_dict = _json_dict(filters)
	export_options = _normalize_options(options)
	payload = _run_report(report_name, filters_dict)
	all_columns = [_column_dict(column, index) for index, column in enumerate(payload.get("columns") or [])]
	rows = _normalize_rows(payload.get("result") or [], all_columns)
	columns = _select_columns(all_columns, export_options["columns"])
	if not columns:
		frappe.throw(_("No report columns are available for export."))
	rows = _slice_rows(rows, export_options, start, page_length)
	summary = payload.get("report_summary") or []
	filename = report_name.replace("/", "-").strip() or "report"
	file_format = export_options["format"]

	if file_format == "pdf":
		content = _pdf_bytes(_pdf_html(report_name, filters_dict, columns, rows, summary, export_options), export_options["orientation"])
	elif file_format == "csv":
		matrix, _ = _table_matrix(report_name, filters_dict, columns, rows, summary, export_options)
		content = _csv_bytes(matrix)
	else:
		matrix, header_index = _table_matrix(report_name, filters_dict, columns, rows, summary, export_options)
		content = _xlsx_bytes(matrix, report_name, header_index, export_options["include_filters"])

	_set_download_response(content, filename, file_format)
