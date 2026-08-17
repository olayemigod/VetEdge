from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services.report_visibility import validate_dashboard_access, validate_report_access


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


def get_reporting_capabilities(scope_name: str, scope_type: str = "report", user: str | None = None) -> dict:
	"""Return shell-action capabilities after the normal scope access gate passes.

	The EdgeSuite shell only renders actions. VetEdge remains authoritative for
	settings, role access, branch/practitioner restrictions and server-side export
	or print authorization.
	"""
	_validate_scope(scope_name, scope_type, user=user)
	return {
		"scope_name": cstr(scope_name or "").strip(),
		"scope_type": cstr(scope_type or "report").strip().lower(),
		"can_view": True,
		"can_print": _setting_enabled(PRINT_SETTING, default=True),
		"can_export": _setting_enabled(EXPORT_SETTING, default=True),
		"authorization_model": "settings_and_scope_access",
	}


def require_reporting_action(
	scope_name: str,
	scope_type: str = "report",
	action: str = "view",
	user: str | None = None,
) -> dict:
	capabilities = get_reporting_capabilities(scope_name, scope_type=scope_type, user=user)
	action = cstr(action or "view").strip().lower()
	if action == "view":
		return capabilities
	if action == "print" and capabilities["can_print"]:
		return capabilities
	if action == "export" and capabilities["can_export"]:
		return capabilities
	if action not in {"print", "export"}:
		frappe.throw(_("Unsupported reporting action."))
	frappe.throw(
		_("{0} is disabled by Veterinary Settings for reports and dashboards.").format(action.title()),
		frappe.PermissionError,
	)


@frappe.whitelist()
def get_shell_capabilities(scope_name: str, scope_type: str = "report") -> dict:
	return get_reporting_capabilities(scope_name, scope_type=scope_type)
