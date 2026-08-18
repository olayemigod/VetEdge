from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services.report_visibility import validate_dashboard_access, validate_report_access
from vetedge.services.reporting_catalog import get_reporting_entitlement, require_reporting_entitlement


PRINT_SETTING = "enable_reporting_print"
EXPORT_SETTING = "enable_reporting_export"


def _setting_enabled(fieldname: str, default: bool = True) -> bool:
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return default
	meta = frappe.get_meta("Veterinary Settings")
	if not meta.has_field(fieldname):
		return default
	value = frappe.db.get_single_value("Veterinary Settings", fieldname)
	if value in (None, ""):
		return default
	return bool(cint(value))


def _validate_scope(scope_name: str, scope_type: str, user: str | None = None) -> None:
	scope_name = cstr(scope_name or "").strip()
	scope_type = cstr(scope_type or "report").strip().lower()
	if not scope_name:
		frappe.throw(_("A report or dashboard scope is required."))
	if scope_type == "dashboard":
		validate_dashboard_access(scope_name, user=user)
	elif scope_type == "report":
		validate_report_access(scope_name, user=user)
	else:
		frappe.throw(_("Unsupported reporting scope type."))


def _report_ref_doctype(report_name: str) -> str:
	if not frappe.db.exists("Report", report_name):
		return ""
	return cstr(frappe.get_cached_value("Report", report_name, "ref_doctype") or "").strip()


def _has_action_permission(scope_name: str, scope_type: str, action: str, user: str | None = None) -> bool:
	"""Apply product/Frappe action permission after the normal scope view gate.

	Dashboards have no single ref_doctype, so their action authorization is the
	dashboard access gate itself in V1. Reports additionally honor the Report
	ref_doctype's Frappe print/export permission when one is declared.
	"""
	if scope_type == "dashboard":
		return True
	ref_doctype = _report_ref_doctype(scope_name)
	if not ref_doctype:
		return True
	return bool(frappe.has_permission(ref_doctype, ptype=action, user=user))


def get_reporting_capabilities(scope_name: str, scope_type: str = "report", user: str | None = None) -> dict:
	"""Return shell capabilities from subscription tier + settings + scope + action permission."""
	scope_name = cstr(scope_name or "").strip()
	scope_type = cstr(scope_type or "report").strip().lower()
	_validate_scope(scope_name, scope_type, user=user)
	entitlement = get_reporting_entitlement(scope_name, scope_type=scope_type, user=user)
	entitled = bool(entitlement["entitled"])
	print_setting = _setting_enabled(PRINT_SETTING, default=True)
	export_setting = _setting_enabled(EXPORT_SETTING, default=True)
	can_print = entitled and print_setting and _has_action_permission(scope_name, scope_type, "print", user=user)
	can_export = entitled and export_setting and _has_action_permission(scope_name, scope_type, "export", user=user)
	return {
		"scope_name": scope_name,
		"scope_type": scope_type,
		"can_view": entitled,
		"can_print": can_print,
		"can_export": can_export,
		"report_tier": entitlement["tier"],
		"is_advanced": entitlement["is_advanced"],
		"subscription_feature_key": entitlement.get("feature_key"),
		"subscription_entitled": entitled,
		"entitlement_source": entitlement["entitlement_source"],
		"entitlement_reason_code": entitlement["entitlement_reason_code"],
		"authorization_model": "subscription_tier_then_settings_scope_and_action_permission",
	}


def require_reporting_action(
	scope_name: str,
	scope_type: str = "report",
	action: str = "view",
	user: str | None = None,
) -> dict:
	capabilities = get_reporting_capabilities(scope_name, scope_type=scope_type, user=user)
	action = cstr(action or "view").strip().lower()
	if not capabilities["can_view"]:
		require_reporting_entitlement(scope_name, scope_type=scope_type, user=user)
	if action == "view":
		return capabilities
	if action == "print" and capabilities["can_print"]:
		return capabilities
	if action == "export" and capabilities["can_export"]:
		return capabilities
	if action not in {"print", "export"}:
		frappe.throw(_("Unsupported reporting action."))
	frappe.throw(
		_("You are not permitted to {0} this report or dashboard, or the capability is disabled in Veterinary Settings.").format(action),
		frappe.PermissionError,
	)


@frappe.whitelist()
def get_shell_capabilities(scope_name: str, scope_type: str = "report") -> dict:
	return get_reporting_capabilities(scope_name, scope_type=scope_type)
