from __future__ import annotations

import frappe

from vetedge.coreedge_adapter import (
	get_current_vetedge_context,
	get_vetedge_product_app,
	is_coreedge_available,
	is_coreedge_enabled,
	should_fail_closed_when_coreedge_missing,
)
from vetedge.services.feature_flags import is_enabled

ADVANCED_REPORTS_FEATURE_KEY = "advanced_reports"


def check_advanced_reporting_entitlement(user: str | None = None) -> dict:
	"""Resolve Advanced Reporting entitlement without duplicating CoreEdge policy.

	Shared-hosted/white-label deployments use CoreEdge's existing Feature
	entitlement engine. Standalone deployments retain the Veterinary Settings
	feature flag as their local compatibility source.
	"""
	user = user or frappe.session.user
	if not is_coreedge_enabled():
		allowed = bool(is_enabled(ADVANCED_REPORTS_FEATURE_KEY))
		return {
			"allowed": allowed,
			"source": "veterinary_settings",
			"feature_key": ADVANCED_REPORTS_FEATURE_KEY,
			"reason_code": "LOCAL_FEATURE_ENABLED" if allowed else "LOCAL_FEATURE_DISABLED",
		}

	if not is_coreedge_available():
		allowed = not should_fail_closed_when_coreedge_missing()
		return {
			"allowed": allowed,
			"source": "coreedge_unavailable",
			"feature_key": ADVANCED_REPORTS_FEATURE_KEY,
			"reason_code": "PLATFORM_MISSING_FAIL_OPEN" if allowed else "PLATFORM_MISSING",
		}

	try:
		from coreedge.coreedge.entitlements import check_entitlement

		context = get_current_vetedge_context(user=user) or {}
		tenant = context.get("tenant")
		product_app = context.get("product_app") or context.get("active_product_app") or get_vetedge_product_app()
		result = check_entitlement(
			user=user,
			tenant=tenant,
			product_app=product_app,
			entitlement_key=ADVANCED_REPORTS_FEATURE_KEY,
			entitlement_type="Feature",
			request_source="System",
			reference_doctype="CoreEdge Entitlement",
			reference_name=ADVANCED_REPORTS_FEATURE_KEY,
			log_result=False,
		) or {}
		return {
			"allowed": bool(result.get("allowed")),
			"source": "coreedge_entitlement",
			"feature_key": ADVANCED_REPORTS_FEATURE_KEY,
			"reason_code": result.get("denial_reason") or result.get("access_result") or "",
			"access_result": result.get("access_result"),
			"upgrade_opportunity": bool(result.get("upgrade_opportunity")),
		}
	except (ImportError, ModuleNotFoundError):
		allowed = not should_fail_closed_when_coreedge_missing()
		return {
			"allowed": allowed,
			"source": "coreedge_entitlement_unavailable",
			"feature_key": ADVANCED_REPORTS_FEATURE_KEY,
			"reason_code": "ENTITLEMENT_RUNTIME_MISSING_FAIL_OPEN" if allowed else "ENTITLEMENT_RUNTIME_MISSING",
		}
