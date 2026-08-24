from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services.portal_access import require_internal_user
from vetedge.services.report_visibility import normalize_report_filters, validate_report_access
from vetedge.services.reporting_catalog import require_reporting_entitlement

PAGE_LENGTH_MAX = 100

# These reports are still backed by their established Script Report execution
# logic, but EdgeSuite must not download the complete result set to the browser.
# Optimized query-level providers remain preferred and are registered separately.
LEGACY_EDGE_REPORTS = frozenset(
	{
		"Practitioner Performance Report",
		"Branch Performance Report",
		"Revenue Summary",
		"Unpaid Invoice Report",
		"Dispensary Activity Report",
		"Stock Usage Summary",
		"Stock Expiry Status",
		"Boarding Report",
		"Kennel Availability Report",
		"Grooming Report",
		"Active Hospitalisations",
		"Hospitalisation Charge Summary",
		"Care Location Occupancy",
		"Hospitalisation Discharge Watch",
		"Pending Hospitalisation Actions",
		"Veterinary Notification Event Registry",
	}
)


def _parse_filters(filters: str | dict | None) -> dict[str, Any]:
	if not filters:
		return {}
	if isinstance(filters, dict):
		return dict(filters)
	parsed = frappe.parse_json(filters)
	if not isinstance(parsed, dict):
		frappe.throw(_("Expected report filters as a JSON object."), frappe.ValidationError)
	return parsed


def _normalize_result_rows(payload: dict[str, Any]) -> list[Any]:
	rows = payload.get("result")
	if rows is None:
		rows = payload.get("rows")
	return list(rows or [])


@frappe.whitelist()
@frappe.read_only()
def get_legacy_report_page(
	report_name: str,
	filters: str | dict | None = None,
	start: int = 0,
	page_length: int = 50,
) -> dict[str, Any]:
	"""Run an allow-listed existing VetEdge report and return a bounded page.

	This is a migration adapter, not a query-level optimization. It preserves the
	established report/accounting logic and permissions while preventing the
	browser from receiving the complete result set. High-volume reports can later
	move to dedicated query-level providers without changing the EdgeSuite shell.
	"""

	require_internal_user()
	report_name = cstr(report_name).strip()
	if report_name not in LEGACY_EDGE_REPORTS:
		frappe.throw(_("This report is not available through the Veterinary EdgeSuite report adapter."), frappe.PermissionError)

	validate_report_access(report_name)
	require_reporting_entitlement(report_name, scope_type="report")
	normalized = dict(normalize_report_filters(report_name, _parse_filters(filters)) or {})

	start = max(cint(start), 0)
	page_length = min(max(cint(page_length) or 50, 1), PAGE_LENGTH_MAX)

	# Use Frappe's own Query Report runner so Report permissions, prepared-report
	# rules and the report's existing accounting/clinical execution logic remain
	# authoritative. The adapter only bounds the response sent to the browser.
	from frappe.desk.query_report import run

	payload = run(
		report_name=report_name,
		filters=frappe.as_json(normalized),
		ignore_prepared_report=True,
		are_default_filters=False,
	)
	payload = dict(payload or {})
	rows = _normalize_result_rows(payload)
	total = len(rows)
	page_rows = rows[start : start + page_length]

	return {
		"columns": payload.get("columns") or [],
		"rows": page_rows,
		"summary": payload.get("report_summary") or payload.get("summary") or [],
		"chart": payload.get("chart"),
		"message": payload.get("message"),
		"total": total,
		"total_count": total,
		"start": start,
		"page_length": page_length,
		"has_previous": start > 0,
		"has_next": start + len(page_rows) < total,
		"metadata": {
			"pagination_mode": "materialize-then-slice",
			"source": "existing-query-report",
			"report_name": report_name,
			"query_level_optimization_pending": True,
		},
	}
