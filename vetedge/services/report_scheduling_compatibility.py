from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cstr

from vetedge.services.portal_access import require_internal_user
from vetedge.services.report_visibility import validate_report_access
from vetedge.services.reporting_catalog import REPORT_CATALOG, get_reporting_entitlement
from vetedge.services.reporting_entitlement_adapter import check_advanced_reporting_entitlement

NATIVE_AUTO_EMAIL = "native_auto_email"
VETEDGE_EXPORT_ADAPTER = "vetedge_export_adapter"
NOT_SCHEDULABLE = "not_schedulable"

# These reports deliberately use VetEdge/EdgeSuite providers whose interactive
# semantics differ from direct Frappe Report execution. Scheduled delivery must
# therefore reuse the VetEdge export/provider layer rather than silently send a
# different dataset through Auto Email Report.
VETEDGE_PROVIDER_REPORTS = {
	"Consultation Register",
	"Planned Treatment",
	"Lab Order Report",
	"Vaccination Report",
	"Patient Register",
	"Owner Register",
	"Stock Expiry Status",
}

REPORT_ALIASES = {
	"Laboratory Report": "Lab Order Report",
	"Stock Expiry Report": "Stock Expiry Status",
	"Stock Expiry Monitor": "Stock Expiry Status",
	"Planned Treatment Report": "Planned Treatment",
}


def canonical_report_name(report_name: str) -> str:
	name = cstr(report_name or "").strip()
	return REPORT_ALIASES.get(name, name)


def _native_report_exists(report_name: str) -> bool:
	return bool(report_name and frappe.db.exists("Report", report_name))


def _auto_email_available() -> bool:
	return bool(frappe.db.exists("DocType", "Auto Email Report"))


def classify_report(report_name: str) -> dict:
	name = canonical_report_name(report_name)
	if not name:
		frappe.throw(_("A report name is required."), frappe.ValidationError)

	if name not in REPORT_CATALOG:
		return {
			"report_name": name,
			"delivery_mode": NOT_SCHEDULABLE,
			"schedulable": False,
			"reason_code": "NOT_IN_VETEDGE_REPORT_CATALOG",
			"native_report_exists": _native_report_exists(name),
			"auto_email_available": _auto_email_available(),
		}

	if name in VETEDGE_PROVIDER_REPORTS:
		return {
			"report_name": name,
			"delivery_mode": VETEDGE_EXPORT_ADAPTER,
			"schedulable": True,
			"reason_code": "VETEDGE_PROVIDER_SEMANTICS",
			"native_report_exists": _native_report_exists(name),
			"auto_email_available": _auto_email_available(),
		}

	native_report = _native_report_exists(name)
	auto_email = _auto_email_available()
	if native_report and auto_email:
		return {
			"report_name": name,
			"delivery_mode": NATIVE_AUTO_EMAIL,
			"schedulable": True,
			"reason_code": "NATIVE_REPORT_COMPATIBLE",
			"native_report_exists": True,
			"auto_email_available": True,
		}

	return {
		"report_name": name,
		"delivery_mode": NOT_SCHEDULABLE,
		"schedulable": False,
		"reason_code": "NATIVE_SCHEDULER_CONTRACT_UNAVAILABLE",
		"native_report_exists": native_report,
		"auto_email_available": auto_email,
	}


def get_report_scheduling_compatibility(report_name: str, user: str | None = None) -> dict:
	name = canonical_report_name(report_name)
	validate_report_access(name, user=user)
	classification = classify_report(name)
	entitlement = get_reporting_entitlement(name, scope_type="report", user=user)
	advanced = check_advanced_reporting_entitlement(user=user)
	return {
		**classification,
		"report_tier": entitlement.get("tier"),
		"report_entitled": bool(entitlement.get("entitled")),
		"scheduled_delivery_entitled": bool(advanced.get("allowed")),
		"scheduled_delivery_feature_key": advanced.get("feature_key") or "advanced_reports",
		"can_configure": bool(classification.get("schedulable") and entitlement.get("entitled") and advanced.get("allowed")),
		"write_performed": False,
	}


@frappe.whitelist()
@frappe.read_only()
def get_scheduling_compatibility(report_name: str) -> dict:
	require_internal_user()
	return get_report_scheduling_compatibility(report_name)


@frappe.whitelist()
@frappe.read_only()
def get_scheduling_compatibility_audit() -> dict:
	require_internal_user()
	items = []
	for report_name in REPORT_CATALOG:
		try:
			items.append(get_report_scheduling_compatibility(report_name))
		except frappe.PermissionError:
			continue
	counts = {NATIVE_AUTO_EMAIL: 0, VETEDGE_EXPORT_ADAPTER: 0, NOT_SCHEDULABLE: 0}
	for item in items:
		counts[item["delivery_mode"]] = counts.get(item["delivery_mode"], 0) + 1
	return {
		"items": items,
		"counts": counts,
		"scheduler_reused": "Frappe Auto Email Report",
		"custom_scheduler_created": False,
		"write_performed": False,
	}
