from __future__ import annotations

import frappe

from vetedge.services.report_export import download_report_export
from vetedge.services.report_print import get_report_print_html
from vetedge.services.reporting_capabilities import require_reporting_action


@frappe.whitelist()
@frappe.read_only()
def download_report(
	report_name: str,
	filters=None,
	options=None,
	start: int = 0,
	page_length: int = 50,
):
	"""Shell export endpoint: re-authorize the report action on every request."""
	require_reporting_action(report_name, scope_type="report", action="export")
	return download_report_export(
		report_name=report_name,
		filters=filters,
		options=options,
		start=start,
		page_length=page_length,
	)


@frappe.whitelist()
@frappe.read_only()
def get_print_html(
	report_name: str,
	filters=None,
	options=None,
	start: int = 0,
	page_length: int = 50,
) -> str:
	"""Shell print endpoint: re-authorize the report action on every request."""
	require_reporting_action(report_name, scope_type="report", action="print")
	return get_report_print_html(
		report_name=report_name,
		filters=filters,
		options=options,
		start=start,
		page_length=page_length,
	)
