from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services.report_scheduling_compatibility import VETEDGE_EXPORT_ADAPTER, get_report_scheduling_compatibility
from vetedge.services.report_visibility import normalize_report_filters

MAX_BRIDGE_ROWS = 5000
PAGE_LENGTH = 100

PROVIDER_METHODS = {
	"Consultation Register": "vetedge.services.consultation_report.get_consultation_register_view",
	"Planned Treatment": "vetedge.services.treatment_plan_report.get_planned_treatment_view",
	"Lab Order Report": "vetedge.services.lab_order_report.get_lab_order_report_view",
	"Vaccination Report": "vetedge.services.vaccination_report.get_vaccination_report_view",
	"Patient Register": "vetedge.services.patient_report.get_patient_register_view",
	"Owner Register": "vetedge.services.owner_report.get_owner_register_view",
}

STOCK_EXPIRY_REPORT = "Stock Expiry Status"
STOCK_EXPIRY_METHOD = "vetedge.veterinary.page.stock_expiry_monitor.stock_expiry_monitor.get_stock_expiry_data"
STOCK_EXPIRY_COLUMNS = [
	{"fieldname": "item_code", "label": _("Item Code"), "fieldtype": "Link", "options": "Item"},
	{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data"},
	{"fieldname": "batch_no", "label": _("Batch No"), "fieldtype": "Link", "options": "Batch"},
	{"fieldname": "warehouse", "label": _("Warehouse"), "fieldtype": "Link", "options": "Warehouse"},
	{"fieldname": "qty", "label": _("Quantity"), "fieldtype": "Float"},
	{"fieldname": "stock_uom", "label": _("UOM"), "fieldtype": "Data"},
	{"fieldname": "expiry_date", "label": _("Expiry Date"), "fieldtype": "Date"},
	{"fieldname": "days_to_expiry", "label": _("Days Left"), "fieldtype": "Int"},
	{"fieldname": "expiry_status", "label": _("Risk Status"), "fieldtype": "Data"},
	{"fieldname": "branch", "label": _("Branch"), "fieldtype": "Link", "options": "Branch"},
]


def _json_dict(value, label: str) -> dict:
	if not value:
		return {}
	if isinstance(value, dict):
		return dict(value)
	try:
		parsed = json.loads(value)
	except (TypeError, ValueError):
		frappe.throw(_("{0} must be valid JSON.").format(label), frappe.ValidationError)
	if not isinstance(parsed, dict):
		frappe.throw(_("{0} must be a JSON object.").format(label), frappe.ValidationError)
	return parsed


def _json_list(value, label: str) -> list[str]:
	if not value:
		return []
	if isinstance(value, list):
		parsed = value
	else:
		try:
			parsed = json.loads(value)
		except (TypeError, ValueError):
			frappe.throw(_("{0} must be valid JSON.").format(label), frappe.ValidationError)
	if not isinstance(parsed, list):
		frappe.throw(_("{0} must be a JSON list.").format(label), frappe.ValidationError)
	return [cstr(item).strip() for item in parsed if cstr(item).strip()]


def _column_key(column: dict, index: int) -> str:
	return cstr(column.get("fieldname") or column.get("key") or f"column_{index + 1}")


def _selected_columns(columns: list[dict], requested: list[str]) -> list[dict]:
	visible = [dict(column) for column in columns if isinstance(column, dict) and not column.get("hidden")]
	if not requested:
		return visible
	allowed = set(requested)
	selected = [column for index, column in enumerate(visible) if _column_key(column, index) in allowed]
	if not selected:
		frappe.throw(_("None of the selected scheduled-report columns are available."), frappe.ValidationError)
	return selected


def _page(report_name: str, filters: dict, start: int, page_length: int) -> dict:
	if report_name == STOCK_EXPIRY_REPORT:
		method = frappe.get_attr(STOCK_EXPIRY_METHOD)
		payload = method(
			filters={
				"warehouse": filters.get("warehouse") or "",
				"item_group": filters.get("item_group") or "",
				"expiry_window": filters.get("expiry_window") or "all",
				"days_threshold": cint(filters.get("days_threshold") or 60),
				"item": filters.get("item") or "",
				"limit": page_length,
				"offset": start,
			}
		) or {}
		return {
			"columns": STOCK_EXPIRY_COLUMNS,
			"rows": payload.get("rows") or [],
			"total": cint(payload.get("total_count")),
		}

	method_path = PROVIDER_METHODS.get(report_name)
	if not method_path:
		frappe.throw(_("No optimized scheduled-report provider is configured for {0}.").format(report_name), frappe.ValidationError)
	payload = frappe.get_attr(method_path)(filters=filters, start=start, page_length=page_length) or {}
	return {
		"columns": payload.get("columns") or [],
		"rows": payload.get("rows") or payload.get("result") or [],
		"total": cint(payload.get("total") or payload.get("total_count")),
	}


def get_scheduled_report_data(report_name: str, filters=None, selected_columns=None, row_limit: int = 500) -> tuple[list[dict], list[dict]]:
	compatibility = get_report_scheduling_compatibility(report_name)
	if not compatibility.get("can_configure") or compatibility.get("delivery_mode") != VETEDGE_EXPORT_ADAPTER:
		frappe.throw(_("This report is not available through the VetEdge scheduled-report adapter."), frappe.PermissionError)

	report_name = compatibility["report_name"]
	normalized_filters = dict(normalize_report_filters(report_name, _json_dict(filters, _("Scheduled report filters"))) or {})
	requested_columns = _json_list(selected_columns, _("Selected columns"))
	row_limit = min(max(cint(row_limit) or 500, 1), MAX_BRIDGE_ROWS)

	rows: list[dict] = []
	columns: list[dict] = []
	start = 0
	while len(rows) < row_limit:
		page_length = min(PAGE_LENGTH, row_limit - len(rows))
		payload = _page(report_name, normalized_filters, start, page_length)
		page_rows = [dict(row) for row in (payload.get("rows") or [])]
		if not columns:
			columns = [dict(column) for column in (payload.get("columns") or []) if isinstance(column, dict)]
		rows.extend(page_rows)
		start += len(page_rows)
		total = cint(payload.get("total"))
		if not page_rows or len(page_rows) < page_length or (total and start >= total):
			break

	columns = _selected_columns(columns, requested_columns)
	allowed_keys = {_column_key(column, index) for index, column in enumerate(columns)}
	rows = [{key: value for key, value in row.items() if key in allowed_keys} for row in rows[:row_limit]]
	return columns, rows
