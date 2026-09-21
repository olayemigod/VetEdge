from __future__ import annotations

import ast
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _text(relative_path: str) -> str:
	return (PACKAGE_ROOT / relative_path).read_text(encoding="utf-8")


def test_legacy_report_pagination_adapter_is_bounded_and_permission_aware():
	source = _text("services/legacy_report_pagination.py")
	ast.parse(source)

	for report in (
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
	):
		assert f'"{report}"' in source

	assert "require_internal_user()" in source
	assert "validate_report_access(report_name)" in source
	assert "require_reporting_entitlement(report_name" in source
	assert "normalize_report_filters(report_name" in source
	assert "from frappe.desk.query_report import run" in source
	assert "ignore_prepared_report=True" in source
	assert "page_rows = rows[start : start + page_length]" in source
	assert '"pagination_mode": "materialize-then-slice"' in source
	assert "PAGE_LENGTH_MAX = 100" in source
	assert "ignore_permissions=True" not in source
	assert "ignore_permissions = True" not in source


def test_report_provider_registry_uses_bounded_legacy_adapter_not_browser_query_runner():
	source = _text("public/js/vetedge_report_provider_registry.js")
	assert "LEGACY_EDGE_REPORTS" in source
	assert "vetedge.services.legacy_report_pagination.get_legacy_report_page" in source
	assert 'pagination_mode: payload.metadata?.pagination_mode || "materialize-then-slice"' in source
	assert 'sorting_mode: "not-supported"' in source
	assert "LEGACY_EDGE_REPORTS.forEach(registerLegacyReport)" in source
