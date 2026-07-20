from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from vetedge.services.permissions import (
	ELEVATED_ROLES,
	get_assigned_branches,
	get_user_roles,
	is_internal_staff_user,
	user_has_global_branch_access,
)

USER_BRANCH_KEY = "vetedge_working_branch"
USER_COMPANY_KEY = "vetedge_working_company"


def _clean(value: Any) -> str:
	return str(value or "").strip()


def _assert_user_scope(user: str) -> None:
	if user == frappe.session.user:
		return
	if not get_user_roles(frappe.session.user).intersection(ELEVATED_ROLES):
		frappe.throw(_("You cannot manage another user's Veterinary branch context."), frappe.PermissionError)


def _branch_fields() -> list[str]:
	meta = frappe.get_meta("Branch")
	fields = ["name"]
	for fieldname in (
		"branch",
		"vetedge_company",
		"vetedge_cost_center",
		"vetedge_default_warehouse",
		"vetedge_price_list",
		"disabled",
	):
		if meta.has_field(fieldname):
			fields.append(fieldname)
	return fields


def _single_site_company() -> str:
	if not frappe.db.exists("DocType", "Company"):
		return ""
	companies = frappe.get_all("Company", pluck="name", limit_page_length=2)
	return _clean(companies[0]) if len(companies) == 1 else ""


def _normalize_branch(row: dict, single_company: str = "") -> dict:
	company = _clean(row.get("vetedge_company")) or single_company
	label = _clean(row.get("branch")) or _clean(row.get("name"))
	return {
		"name": _clean(row.get("name")),
		"value": _clean(row.get("name")),
		"branch_name": label,
		"label": label,
		"branch_code": "",
		"code": "",
		"company": company,
		"cost_center": _clean(row.get("vetedge_cost_center")),
		"default_warehouse": _clean(row.get("vetedge_default_warehouse")),
		"price_list": _clean(row.get("vetedge_price_list")),
		"configured": bool(company),
		"disabled": not bool(company),
	}


def get_allowed_veterinary_branches(*, user: str | None = None, company: str | None = None) -> list[dict]:
	resolved_user = user or frappe.session.user
	_assert_user_scope(resolved_user)
	if not is_internal_staff_user(resolved_user):
		return []
	if not frappe.db.exists("DocType", "Branch"):
		return []

	assigned = list(dict.fromkeys(get_assigned_branches(resolved_user)))
	filters: dict[str, Any] = {}
	meta = frappe.get_meta("Branch")
	if meta.has_field("disabled"):
		filters["disabled"] = ["!=", 1]
	if assigned and not user_has_global_branch_access(resolved_user):
		filters["name"] = ["in", assigned]

	rows = frappe.get_all(
		"Branch",
		filters=filters,
		fields=_branch_fields(),
		order_by="name asc",
		limit_page_length=500,
	)
	single_company = _single_site_company()
	result = [_normalize_branch(row, single_company) for row in rows]
	if company:
		result = [row for row in result if row.get("company") == company]
	return result


def _default_branch(allowed: list[dict]) -> str:
	configured = [row for row in allowed if row.get("configured")]
	if len(configured) == 1:
		return configured[0]["name"]
	return ""


def get_working_branch_name(*, user: str | None = None) -> str:
	resolved_user = user or frappe.session.user
	_assert_user_scope(resolved_user)
	allowed = {row["name"]: row for row in get_allowed_veterinary_branches(user=resolved_user)}
	current = _clean(frappe.defaults.get_user_default(USER_BRANCH_KEY, user=resolved_user))
	if current and current in allowed and allowed[current].get("configured"):
		return current
	if current:
		frappe.defaults.clear_default(USER_BRANCH_KEY, parent=resolved_user)
	return _default_branch(list(allowed.values()))


def get_working_company(*, user: str | None = None) -> str:
	resolved_user = user or frappe.session.user
	branch = get_working_branch_name(user=resolved_user)
	if branch:
		for row in get_allowed_veterinary_branches(user=resolved_user):
			if row["name"] == branch:
				return _clean(row.get("company"))
	return _clean(frappe.defaults.get_user_default(USER_COMPANY_KEY, user=resolved_user))


def get_active_veterinary_branch_context(*, user: str | None = None) -> dict:
	resolved_user = user or frappe.session.user
	_assert_user_scope(resolved_user)
	allowed = get_allowed_veterinary_branches(user=resolved_user)
	allowed_map = {row["name"]: row for row in allowed}
	current_name = get_working_branch_name(user=resolved_user)
	current = allowed_map.get(current_name)
	configured = [row for row in allowed if row.get("configured")]
	can_switch = user_has_global_branch_access(resolved_user) or len(configured) > 1
	return {
		"current_branch": current,
		"active_branch": current_name or None,
		"active_company": (current or {}).get("company") or get_working_company(user=resolved_user) or None,
		"active_label": (current or {}).get("branch_name") or _("Select working branch"),
		"active_defaults": {
			"company": (current or {}).get("company") or "",
			"cost_center": (current or {}).get("cost_center") or "",
			"warehouse": (current or {}).get("default_warehouse") or "",
			"price_list": (current or {}).get("price_list") or "",
		},
		"allowed_branches": allowed,
		"configured_branches": configured,
		"can_switch_branch": can_switch,
		"requires_branch_selection": bool(configured and not current),
		"unconfigured_branch_count": len([row for row in allowed if not row.get("configured")]),
		"legacy_assignment_fallback": not bool(get_assigned_branches(resolved_user)),
	}


def validate_working_branch(branch: str | None, *, company: str | None = None, user: str | None = None) -> dict:
	resolved_user = user or frappe.session.user
	branch = _clean(branch)
	allowed = {row["name"]: row for row in get_allowed_veterinary_branches(user=resolved_user)}
	if not branch or branch not in allowed:
		frappe.throw(_("Select a permitted Veterinary working branch."), frappe.PermissionError)
	row = allowed[branch]
	if not row.get("company"):
		frappe.throw(
			_("Configure Veterinary Company on Branch {0} before using it as a working branch.").format(branch),
			frappe.ValidationError,
		)
	if company and row.get("company") != company:
		frappe.throw(
			_("Branch {0} belongs to Company {1}, not Company {2}.").format(branch, row.get("company"), company),
			frappe.ValidationError,
		)
	return row


@frappe.whitelist()
def get_branch_context() -> dict:
	if frappe.session.user == "Guest":
		frappe.throw(_("Authentication required."), frappe.PermissionError)
	return get_active_veterinary_branch_context()


@frappe.whitelist()
def switch_veterinary_branch(branch: str) -> dict:
	if frappe.session.user == "Guest":
		frappe.throw(_("Authentication required."), frappe.PermissionError)
	row = validate_working_branch(branch)
	frappe.defaults.set_user_default(USER_BRANCH_KEY, row["name"], user=frappe.session.user)
	frappe.defaults.set_user_default(USER_COMPANY_KEY, row["company"], user=frappe.session.user)
	frappe.defaults.set_user_default("company", row["company"], user=frappe.session.user)
	frappe.defaults.set_user_default("branch", row["name"], user=frappe.session.user)
	frappe.clear_cache(user=frappe.session.user)
	return get_active_veterinary_branch_context()
