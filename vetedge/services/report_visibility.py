from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cstr

from vetedge.services.permissions import (
	ELEVATED_ROLES,
	ROLE_ACCOUNTS_CASHIER,
	ROLE_ACCOUNTS_MANAGER,
	ROLE_BRANCH_MANAGER,
	ROLE_DISPENSARY_USER,
	ROLE_LAB_TECHNICIAN,
	ROLE_SYSTEM_MANAGER,
	ROLE_VETEDGE_ADMINISTRATOR,
	ROLE_VETEDGE_DOCTOR,
	ROLE_VETEDGE_FRONT_DESK,
	ROLE_VETEDGE_GROOMER,
	ROLE_VETEDGE_NURSE,
	ROLE_VETERINARY_NURSE,
	get_assigned_branches,
	get_current_user,
	get_user_roles,
	is_portal_owner_user,
	user_has_global_branch_access,
)


def _role_group(*roles: str) -> set[str]:
	group: set[str] = set()
	aliases = {
		ROLE_BRANCH_MANAGER: {ROLE_BRANCH_MANAGER, "VetEdge Branch Manager"},
		ROLE_DISPENSARY_USER: {ROLE_DISPENSARY_USER, "VetEdge Dispensary User"},
		ROLE_LAB_TECHNICIAN: {ROLE_LAB_TECHNICIAN, "VetEdge Lab Technician"},
		ROLE_ACCOUNTS_CASHIER: {ROLE_ACCOUNTS_CASHIER, "VetEdge Accounts/Cashier"},
		ROLE_VETERINARY_NURSE: {ROLE_VETERINARY_NURSE, ROLE_VETEDGE_NURSE},
	}
	for role in roles:
		group |= aliases.get(role, {role})
	return group


ADMIN_REPORTING_ROLES = {ROLE_SYSTEM_MANAGER, ROLE_VETEDGE_ADMINISTRATOR}
BRANCH_MANAGER_REPORTING_ROLES = _role_group(ROLE_BRANCH_MANAGER)
DOCTOR_REPORTING_ROLES = {ROLE_VETEDGE_DOCTOR}
NURSE_REPORTING_ROLES = _role_group(ROLE_VETERINARY_NURSE)
LAB_REPORTING_ROLES = _role_group(ROLE_LAB_TECHNICIAN)
DISPENSARY_REPORTING_ROLES = _role_group(ROLE_DISPENSARY_USER)
FRONT_DESK_REPORTING_ROLES = {ROLE_VETEDGE_FRONT_DESK}
GROOMING_REPORTING_ROLES = {ROLE_VETEDGE_GROOMER}
FINANCE_REPORTING_ROLES = {
	ROLE_ACCOUNTS_MANAGER,
	"Sales Manager",
	*_role_group(ROLE_ACCOUNTS_CASHIER),
}

ALL_ROLES = {
	*ADMIN_REPORTING_ROLES,
	*BRANCH_MANAGER_REPORTING_ROLES,
	*DOCTOR_REPORTING_ROLES,
	*NURSE_REPORTING_ROLES,
	*LAB_REPORTING_ROLES,
	*DISPENSARY_REPORTING_ROLES,
	*FRONT_DESK_REPORTING_ROLES,
	*GROOMING_REPORTING_ROLES,
	*FINANCE_REPORTING_ROLES,
}

REPORT_ROLE_MAP = {
	"Consultation Register": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
		*DOCTOR_REPORTING_ROLES,
		*NURSE_REPORTING_ROLES,
		*FRONT_DESK_REPORTING_ROLES,
	},
	"Patient Register": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
		*DOCTOR_REPORTING_ROLES,
		*NURSE_REPORTING_ROLES,
		*FRONT_DESK_REPORTING_ROLES,
	},
	"Owner Register": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
		*FRONT_DESK_REPORTING_ROLES,
	},
	"Practitioner Performance Report": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
		*DOCTOR_REPORTING_ROLES,
	},
	"Branch Performance Report": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
	},
	"Branch Performance Summary": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
		*FINANCE_REPORTING_ROLES,
	},
	"Revenue Summary": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
		*FINANCE_REPORTING_ROLES,
	},
	"Unpaid Invoice Report": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
		*FINANCE_REPORTING_ROLES,
	},
	"Dispensary Activity Report": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
		*DISPENSARY_REPORTING_ROLES,
	},
	"Stock Usage Summary": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
		*DISPENSARY_REPORTING_ROLES,
	},
	"Lab Order Report": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
		*DOCTOR_REPORTING_ROLES,
		*NURSE_REPORTING_ROLES,
		*LAB_REPORTING_ROLES,
	},
	"Vaccination Report": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
		*DOCTOR_REPORTING_ROLES,
		*NURSE_REPORTING_ROLES,
	},
	"Boarding Report": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
		*FRONT_DESK_REPORTING_ROLES,
	},
	"Kennel Availability Report": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
		*FRONT_DESK_REPORTING_ROLES,
	},
	"Grooming Report": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
		*FRONT_DESK_REPORTING_ROLES,
		*GROOMING_REPORTING_ROLES,
	},
}

DASHBOARD_ROLE_MAP = {
	"executive": {*ADMIN_REPORTING_ROLES},
	"clinical": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
		*DOCTOR_REPORTING_ROLES,
		*NURSE_REPORTING_ROLES,
	},
	"financial": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
		*FINANCE_REPORTING_ROLES,
	},
	"practitioner_performance": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
		*DOCTOR_REPORTING_ROLES,
	},
	"branch_performance": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
	},
	"inventory_dispensary": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
		*DISPENSARY_REPORTING_ROLES,
	},
	"lab": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
		*DOCTOR_REPORTING_ROLES,
		*NURSE_REPORTING_ROLES,
		*LAB_REPORTING_ROLES,
	},
	"vaccination": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
		*DOCTOR_REPORTING_ROLES,
		*NURSE_REPORTING_ROLES,
	},
	"boarding": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
		*FRONT_DESK_REPORTING_ROLES,
	},
	"grooming": {
		*ADMIN_REPORTING_ROLES,
		*BRANCH_MANAGER_REPORTING_ROLES,
		*FRONT_DESK_REPORTING_ROLES,
		*GROOMING_REPORTING_ROLES,
	},
}

BRANCH_SCOPED_ROLES = {
	*BRANCH_MANAGER_REPORTING_ROLES,
	*DOCTOR_REPORTING_ROLES,
	*NURSE_REPORTING_ROLES,
	*LAB_REPORTING_ROLES,
	*DISPENSARY_REPORTING_ROLES,
	*FRONT_DESK_REPORTING_ROLES,
	*GROOMING_REPORTING_ROLES,
}

BRANCH_FILTERED_REPORTS = {
	"Consultation Register",
	"Patient Register",
	"Owner Register",
	"Practitioner Performance Report",
	"Branch Performance Report",
	"Branch Performance Summary",
	"Revenue Summary",
	"Unpaid Invoice Report",
	"Dispensary Activity Report",
	"Stock Usage Summary",
	"Lab Order Report",
	"Vaccination Report",
	"Boarding Report",
	"Kennel Availability Report",
	"Grooming Report",
}

PRACTITIONER_SELF_VIEW_KEYS = {"Practitioner Performance Report", "practitioner_performance"}


@frappe.whitelist()
def get_visibility_context(scope_name: str, scope_type: str = "report") -> dict:
	user = get_current_user()
	scope_name = cstr(scope_name or "").strip()
	scope_type = cstr(scope_type or "report").strip().lower()
	filters = normalize_scope_filters(scope_name, frappe._dict(), scope_type=scope_type, user=user)
	return {
		"default_branch": cstr(filters.get("branch") or ""),
		"allowed_branches": _allowed_branches_for_user(user),
		"practitioner": cstr(filters.get("practitioner") or ""),
		"practitioner_locked": _should_lock_practitioner_view(user, scope_name, scope_type),
	}


def normalize_report_filters(report_name: str, filters=None, user: str | None = None):
	return normalize_scope_filters(report_name, filters, scope_type="report", user=user)


def normalize_dashboard_filters(dashboard_key: str, filters=None, user: str | None = None):
	return normalize_scope_filters(dashboard_key, filters, scope_type="dashboard", user=user)


def validate_dashboard_access(dashboard_key: str, user: str | None = None) -> None:
	user = user or get_current_user()
	if is_portal_owner_user(user):
		frappe.throw(_("You are not permitted to access internal dashboards."), frappe.PermissionError)

	allowed_roles = DASHBOARD_ROLE_MAP.get(cstr(dashboard_key or "").strip(), ALL_ROLES)
	if allowed_roles and not (get_user_roles(user) & allowed_roles):
		frappe.throw(_("You are not permitted to access this dashboard."), frappe.PermissionError)


def normalize_scope_filters(scope_name: str, filters=None, scope_type: str = "report", user: str | None = None):
	user = user or get_current_user()
	filters = frappe._dict(filters or {})
	scope_name = cstr(scope_name or "").strip()
	scope_type = cstr(scope_type or "report").strip().lower()

	if scope_type == "dashboard":
		validate_dashboard_access(scope_name, user=user)
	elif scope_type == "report":
		validate_report_access(scope_name, user=user)

	if _is_branch_filtered_scope(scope_name, scope_type):
		_apply_branch_default_and_restriction(filters, user)

	if _should_lock_practitioner_view(user, scope_name, scope_type):
		filters.practitioner = user

	return filters


def validate_report_access(report_name: str, user: str | None = None) -> None:
	user = user or get_current_user()
	if is_portal_owner_user(user):
		frappe.throw(_("You are not permitted to access internal reports."), frappe.PermissionError)

	allowed_roles = REPORT_ROLE_MAP.get(cstr(report_name or "").strip(), ALL_ROLES)
	if allowed_roles and not (get_user_roles(user) & allowed_roles):
		frappe.throw(_("You are not permitted to access this report."), frappe.PermissionError)


def _apply_branch_default_and_restriction(filters, user: str | None) -> None:
	if not _is_branch_scoped_user(user):
		return

	assigned_branches = _allowed_branches_for_user(user)
	if not assigned_branches:
		return

	selected_branch = cstr(filters.get("branch") or "").strip()
	if selected_branch:
		if selected_branch not in assigned_branches:
			frappe.throw(_("You are not permitted to view records for branch {0}.").format(selected_branch), frappe.PermissionError)
		return

	default_branch = _default_branch_for_user(user, assigned_branches)
	if default_branch:
		filters.branch = default_branch


def _default_branch_for_user(user: str | None, assigned_branches: list[str]) -> str:
	if not assigned_branches:
		return ""

	user_default = ""
	try:
		user_default = cstr(frappe.defaults.get_user_default("Branch") or "").strip()
	except Exception:
		user_default = ""

	if user_default and user_default in assigned_branches:
		return user_default

	if len(assigned_branches) == 1:
		return assigned_branches[0]

	return sorted(assigned_branches)[0]


def _allowed_branches_for_user(user: str | None) -> list[str]:
	if user_has_global_branch_access(user):
		return []
	assigned = [cstr(branch).strip() for branch in get_assigned_branches(user) if cstr(branch).strip()]
	return sorted(dict.fromkeys(assigned))


def _is_branch_scoped_user(user: str | None) -> bool:
	if not user or user_has_global_branch_access(user):
		return False
	return bool(get_user_roles(user) & BRANCH_SCOPED_ROLES)


def _is_branch_filtered_scope(scope_name: str, scope_type: str) -> bool:
	if scope_type == "dashboard":
		return cstr(scope_name or "").strip() in DASHBOARD_ROLE_MAP
	return cstr(scope_name or "").strip() in BRANCH_FILTERED_REPORTS


def _should_lock_practitioner_view(user: str | None, scope_name: str, scope_type: str) -> bool:
	if not user or scope_name not in PRACTITIONER_SELF_VIEW_KEYS:
		return False
	if get_user_roles(user) & ELEVATED_ROLES:
		return False
	if get_user_roles(user) & BRANCH_MANAGER_REPORTING_ROLES:
		return False
	return bool(get_user_roles(user) & DOCTOR_REPORTING_ROLES)
