from __future__ import annotations

from collections.abc import Iterable

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services.permissions import (
	ROLE_ACCOUNTS_CASHIER,
	ROLE_ACCOUNTS_USER,
	ROLE_ALIASES,
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
	can_manage_role_bundles,
	get_current_user,
	get_user_roles,
	validate_role_bundle as validate_role_bundle_base,
)
from vetedge.services.portal_access import require_internal_user

# Veterinary administrators may delegate only product-operational roles. Framework
# administration and broad ERPNext manager roles intentionally stay outside this
# list so a Veterinary Role Bundle cannot become a privilege-escalation path.
ROLE_BUNDLE_SAFE_ASSIGNABLE_ROLES: set[str] = {
	ROLE_VETEDGE_ADMINISTRATOR,
	ROLE_VETEDGE_DOCTOR,
	ROLE_VETEDGE_FRONT_DESK,
	ROLE_VETEDGE_GROOMER,
	ROLE_VETEDGE_NURSE,
	ROLE_VETERINARY_NURSE,
	ROLE_DISPENSARY_USER,
	ROLE_LAB_TECHNICIAN,
	ROLE_BRANCH_MANAGER,
	ROLE_ACCOUNTS_CASHIER,
	ROLE_ACCOUNTS_USER,
	"Desk User",
	"Workspace Manager",
	"Report Manager",
	"Sales User",
	"Stock User",
}
for _aliases in ROLE_ALIASES.values():
	ROLE_BUNDLE_SAFE_ASSIGNABLE_ROLES.update(_aliases)


def is_system_manager(user: str | None = None) -> bool:
	user = user or get_current_user()
	return bool(user and ROLE_SYSTEM_MANAGER in get_user_roles(user))


def get_assignable_role_names(user: str | None = None) -> set[str] | None:
	"""Return assignable roles for the actor; None means System Manager may use any valid Role."""
	if is_system_manager(user):
		return None
	return set(ROLE_BUNDLE_SAFE_ASSIGNABLE_ROLES)


def can_assign_role_from_bundle(role: str | None, user: str | None = None) -> bool:
	role = cstr(role).strip()
	if not role:
		return False
	allowed = get_assignable_role_names(user)
	return allowed is None or role in allowed


def validate_assignable_roles(roles: Iterable[str], user: str | None = None) -> list[str]:
	cleaned: list[str] = []
	for value in roles or []:
		role = cstr(value).strip()
		if not role or role in cleaned:
			continue
		if not can_assign_role_from_bundle(role, user=user):
			frappe.throw(
				_("Role {0} can only be delegated by System Manager and cannot be assigned through this Veterinary Role Bundle.").format(role),
				frappe.PermissionError,
			)
		cleaned.append(role)
	return cleaned


def validate_role_bundle_document(doc, user: str | None = None) -> None:
	"""Preserve existing bundle validation, then enforce actor-level delegation authority."""
	validate_role_bundle_base(doc)
	validate_assignable_roles(
		[row.role for row in (doc.get("roles") or []) if getattr(row, "role", None)],
		user=user,
	)


@frappe.whitelist()
@frappe.read_only()
def search_assignable_role_options(query: str = "", page_length: int = 20) -> list[dict]:
	"""Bounded role search for EdgeSuite role-bundle editing.

	System Manager may search all enabled Frappe Roles. Veterinary administrators see
	only the approved operational delegation set. Backend save/apply checks remain
	authoritative even if the client bypasses this search endpoint.
	"""
	require_internal_user()
	user = get_current_user()
	can_manage_role_bundles(user, raise_exception=True)
	if not frappe.has_permission("Role", "read"):
		return []

	page_length = min(max(cint(page_length) or 20, 1), 50)
	text = cstr(query).strip()
	meta = frappe.get_meta("Role")
	filters = {"disabled": 0} if meta.has_field("disabled") else {}
	allowed = get_assignable_role_names(user)
	if allowed is not None:
		filters["name"] = ["in", sorted(allowed)]
	if text:
		filters["name"] = ["like", f"%{text}%"] if allowed is None else ["in", sorted(role for role in allowed if text.lower() in role.lower())]

	rows = frappe.get_list(
		"Role",
		fields=["name"],
		filters=filters,
		order_by="name asc",
		page_length=page_length,
	)
	return [{"value": row.name, "label": row.name, "description": ""} for row in rows]
