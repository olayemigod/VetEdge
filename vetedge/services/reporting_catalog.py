from __future__ import annotations

from copy import deepcopy

import frappe
from frappe import _

from vetedge.coreedge_adapter import check_vetedge_feature_access, is_coreedge_enabled
from vetedge.services.feature_flags import is_enabled

STANDARD_TIER = "standard"
ADVANCED_TIER = "advanced"
ADVANCED_REPORTS_FEATURE_KEY = "advanced_reports"

# Keep report/dashboard tiering centralized. Unknown resources deliberately fall
# back to Standard so a newly-added operational report is not accidentally
# hidden before it is classified and reviewed for subscription packaging.
REPORT_CATALOG = {
	"Consultation Register": {"tier": STANDARD_TIER},
	"Planned Treatment": {"tier": STANDARD_TIER},
	"Lab Order Report": {"tier": STANDARD_TIER},
	"Vaccination Report": {"tier": STANDARD_TIER},
	"Patient Register": {"tier": STANDARD_TIER},
	"Owner Register": {"tier": STANDARD_TIER},
	"Boarding Report": {"tier": STANDARD_TIER},
	"Grooming Report": {"tier": STANDARD_TIER},
	"Active Hospitalisations": {"tier": STANDARD_TIER},
	"Hospitalisation Charge Summary": {"tier": STANDARD_TIER},
	"Care Location Occupancy": {"tier": STANDARD_TIER},
	"Hospitalisation Discharge Watch": {"tier": STANDARD_TIER},
	"Pending Hospitalisation Actions": {"tier": STANDARD_TIER},
	"Veterinary Notification Registry Admin": {"tier": STANDARD_TIER},
	"Stock Expiry Status": {
		"tier": ADVANCED_TIER,
		"feature_key": ADVANCED_REPORTS_FEATURE_KEY,
		"reason": "inventory_risk_intelligence",
	},
	"Branch Performance Report": {
		"tier": ADVANCED_TIER,
		"feature_key": ADVANCED_REPORTS_FEATURE_KEY,
		"reason": "management_performance_intelligence",
	},
	"Branch Performance Summary": {
		"tier": ADVANCED_TIER,
		"feature_key": ADVANCED_REPORTS_FEATURE_KEY,
		"reason": "management_performance_intelligence",
	},
	"Practitioner Performance Report": {
		"tier": ADVANCED_TIER,
		"feature_key": ADVANCED_REPORTS_FEATURE_KEY,
		"reason": "management_performance_intelligence",
	},
	"Revenue Summary": {
		"tier": ADVANCED_TIER,
		"feature_key": ADVANCED_REPORTS_FEATURE_KEY,
		"reason": "financial_intelligence",
	},
	"Service Revenue Report": {
		"tier": ADVANCED_TIER,
		"feature_key": ADVANCED_REPORTS_FEATURE_KEY,
		"reason": "financial_intelligence",
	},
	"Unpaid Invoice Report": {
		"tier": ADVANCED_TIER,
		"feature_key": ADVANCED_REPORTS_FEATURE_KEY,
		"reason": "financial_intelligence",
	},
	"Dispensary Activity Report": {"tier": STANDARD_TIER},
	"Stock Usage Summary": {
		"tier": ADVANCED_TIER,
		"feature_key": ADVANCED_REPORTS_FEATURE_KEY,
		"reason": "inventory_intelligence",
	},
}

DASHBOARD_CATALOG = {
	"clinical": {"tier": STANDARD_TIER},
	"lab": {"tier": STANDARD_TIER},
	"vaccination": {"tier": STANDARD_TIER},
	"hospitalisation": {"tier": STANDARD_TIER},
	"boarding": {"tier": STANDARD_TIER},
	"grooming": {"tier": STANDARD_TIER},
	"inventory_dispensary": {
		"tier": ADVANCED_TIER,
		"feature_key": ADVANCED_REPORTS_FEATURE_KEY,
		"reason": "inventory_intelligence",
	},
	"executive": {
		"tier": ADVANCED_TIER,
		"feature_key": ADVANCED_REPORTS_FEATURE_KEY,
		"reason": "executive_intelligence",
	},
	"financial": {
		"tier": ADVANCED_TIER,
		"feature_key": ADVANCED_REPORTS_FEATURE_KEY,
		"reason": "financial_intelligence",
	},
	"branch_performance": {
		"tier": ADVANCED_TIER,
		"feature_key": ADVANCED_REPORTS_FEATURE_KEY,
		"reason": "management_performance_intelligence",
	},
	"practitioner_performance": {
		"tier": ADVANCED_TIER,
		"feature_key": ADVANCED_REPORTS_FEATURE_KEY,
		"reason": "management_performance_intelligence",
	},
}


def get_reporting_definition(scope_name: str, scope_type: str = "report") -> dict:
	scope_type = str(scope_type or "report").strip().lower()
	catalog = DASHBOARD_CATALOG if scope_type == "dashboard" else REPORT_CATALOG
	definition = deepcopy(catalog.get(str(scope_name or "").strip()) or {"tier": STANDARD_TIER})
	definition.setdefault("tier", STANDARD_TIER)
	definition.setdefault("feature_key", None)
	definition.setdefault("reason", "operational_reporting")
	definition["scope_name"] = str(scope_name or "").strip()
	definition["scope_type"] = scope_type
	definition["is_advanced"] = definition["tier"] == ADVANCED_TIER
	return definition


def _advanced_entitlement(user: str | None = None) -> dict:
	user = user or frappe.session.user
	if is_coreedge_enabled():
		result = check_vetedge_feature_access(ADVANCED_REPORTS_FEATURE_KEY, user=user) or {}
		allowed = bool(result.get("allowed", result.get("access_result") == "Allowed"))
		return {
			"allowed": allowed,
			"source": "coreedge",
			"feature_key": ADVANCED_REPORTS_FEATURE_KEY,
			"reason_code": result.get("primary_reason_code") or result.get("reason_code") or "",
		}

	return {
		"allowed": bool(is_enabled("advanced_reports")),
		"source": "veterinary_settings",
		"feature_key": ADVANCED_REPORTS_FEATURE_KEY,
		"reason_code": "LOCAL_FEATURE_ENABLED" if is_enabled("advanced_reports") else "LOCAL_FEATURE_DISABLED",
	}


def get_reporting_entitlement(scope_name: str, scope_type: str = "report", user: str | None = None) -> dict:
	definition = get_reporting_definition(scope_name, scope_type)
	if not definition["is_advanced"]:
		return {
			**definition,
			"entitled": True,
			"entitlement_source": "standard_included",
			"entitlement_reason_code": "STANDARD_INCLUDED",
		}

	entitlement = _advanced_entitlement(user=user)
	return {
		**definition,
		"entitled": bool(entitlement["allowed"]),
		"entitlement_source": entitlement["source"],
		"entitlement_reason_code": entitlement["reason_code"],
	}


def require_reporting_entitlement(scope_name: str, scope_type: str = "report", user: str | None = None) -> dict:
	entitlement = get_reporting_entitlement(scope_name, scope_type, user=user)
	if entitlement["entitled"]:
		return entitlement

	frappe.throw(
		_("This is an Advanced report or dashboard and is not included in the current Plan."),
		frappe.PermissionError,
		title=_("Advanced Reporting Access Required"),
	)
