from __future__ import annotations

import frappe
from frappe.utils import cint

from vetedge.services.audit import log_operational_event
from vetedge.services.permissions import (
	ROLE_ACCOUNTS_CASHIER,
	ROLE_ACCOUNTS_USER,
	ROLE_BRANCH_MANAGER,
	ROLE_DISPENSARY_USER,
	ROLE_LAB_TECHNICIAN,
	ROLE_VETEDGE_ADMINISTRATOR,
	ROLE_VETEDGE_DOCTOR,
	ROLE_VETEDGE_GROOMER,
	ROLE_VETEDGE_FRONT_DESK,
	ROLE_VETERINARY_NURSE,
	can_apply_role_bundle,
	can_manage_role_bundles,
)
from vetedge.services.role_bundle_security import validate_role_bundle_document


STARTER_ROLE_BUNDLES = {
	"VetEdge Administrator": [
		ROLE_VETEDGE_ADMINISTRATOR,
		"Desk User",
		"Workspace Manager",
		"Report Manager",
		ROLE_ACCOUNTS_USER,
		"Sales User",
		"Stock User",
	],
	"Veterinary Doctor": [
		ROLE_VETEDGE_DOCTOR,
		"Desk User",
		ROLE_ACCOUNTS_USER,
		"Sales User",
		"Stock User",
	],
	"Veterinary Nurse": [
		ROLE_VETERINARY_NURSE,
		"Desk User",
		"Stock User",
	],
	"Front Desk": [
		ROLE_VETEDGE_FRONT_DESK,
		"Desk User",
		ROLE_ACCOUNTS_USER,
		"Sales User",
	],
	"Grooming Staff": [
		ROLE_VETEDGE_GROOMER,
		"Desk User",
	],
	"Dispensary User": [
		ROLE_DISPENSARY_USER,
		"Desk User",
		ROLE_ACCOUNTS_USER,
		"Stock User",
		"Sales User",
	],
	"Lab Technician": [
		ROLE_LAB_TECHNICIAN,
		"Desk User",
		"Stock User",
	],
	"Branch Manager": [
		ROLE_BRANCH_MANAGER,
		"Desk User",
		ROLE_ACCOUNTS_USER,
		"Sales User",
		"Stock User",
	],
	"Accounts/Cashier": [
		ROLE_ACCOUNTS_CASHIER,
		"Desk User",
		ROLE_ACCOUNTS_USER,
		"Sales User",
	],
}

STARTER_BUNDLE_PRIMARY_ROLES = {
	bundle_name: roles[0]
	for bundle_name, roles in STARTER_ROLE_BUNDLES.items()
	if roles
}


def ensure_starter_role_bundles() -> None:
	if not frappe.db.exists("DocType", "Veterinary Role Bundle"):
		return

	for bundle_name, roles in STARTER_ROLE_BUNDLES.items():
		if frappe.db.exists("Veterinary Role Bundle", bundle_name):
			bundle = frappe.get_doc("Veterinary Role Bundle", bundle_name)
			existing_roles = {row.role for row in bundle.get("roles") or []}
			changed = False
			for role in roles:
				if role not in existing_roles:
					bundle.append("roles", {"role": role})
					changed = True
			if changed:
				bundle.save(ignore_permissions=True)
			continue

		bundle = frappe.get_doc(
			{
				"doctype": "Veterinary Role Bundle",
				"bundle_name": bundle_name,
				"is_active": 1,
				"roles": [{"role": role} for role in roles],
			}
		)
		bundle.insert(ignore_permissions=True)


def ensure_existing_internal_users_have_starter_bundle_roles() -> None:
	if not frappe.db.exists("DocType", "Has Role"):
		return

	for bundle_name, primary_role in STARTER_BUNDLE_PRIMARY_ROLES.items():
		users = frappe.get_all(
			"Has Role",
			filters={
				"role": primary_role,
				"parenttype": "User",
			},
			pluck="parent",
		)
		if not users:
			continue

		bundle_roles = list(dict.fromkeys(STARTER_ROLE_BUNDLES.get(bundle_name, [])))
		for user in users:
			ensure_user_has_roles(user, bundle_roles)


def ensure_user_has_roles(user: str, roles: list[str]) -> list[str]:
	user_doc = frappe.get_doc("User", user)
	existing_roles = {row.role for row in user_doc.get("roles") or []}
	added_roles: list[str] = []

	for role in roles:
		if not role or role in existing_roles:
			continue
		user_doc.add_roles(role)
		existing_roles.add(role)
		added_roles.append(role)

	return added_roles


@frappe.whitelist()
def apply_role_bundle_to_user(bundle_name: str, target_user: str) -> dict:
	return apply_role_bundle(bundle_name, target_user)


def apply_role_bundle(bundle_name: str, target_user: str, acting_user: str | None = None) -> dict:
	acting_user = acting_user or _get_current_user()
	can_apply_role_bundle(acting_user, target_user, raise_exception=True)

	if not frappe.db.exists("User", target_user):
		frappe.throw("Target user must be a valid User.", frappe.ValidationError)

	bundle = frappe.get_doc("Veterinary Role Bundle", bundle_name)
	if cint(getattr(bundle, "is_active", 1)) != 1:
		frappe.throw("Only active role bundles can be applied.", frappe.ValidationError)

	# Revalidate at application time as well as on bundle save. This blocks a
	# Veterinary administrator from applying any historical or externally-created
	# bundle containing a role that only System Manager may delegate.
	validate_role_bundle_document(bundle, user=acting_user)

	user_doc = frappe.get_doc("User", target_user)
	existing_roles = {row.role for row in user_doc.get("roles") or []}
	bundle_roles = []
	added_roles = []

	for row in bundle.get("roles") or []:
		if not row.role:
			continue
		if row.role not in bundle_roles:
			bundle_roles.append(row.role)
		if row.role in existing_roles:
			continue
		user_doc.add_roles(row.role)
		added_roles.append(row.role)
		existing_roles.add(row.role)

	log_operational_event(
		"role_bundle_applied",
		"allowed",
		user=acting_user,
		reference_doctype="User",
		reference_name=target_user,
		details={
			"bundle": bundle_name,
			"bundle_roles": bundle_roles,
			"added_roles": added_roles,
		},
	)

	return {
		"bundle": bundle_name,
		"user": target_user,
		"bundle_roles": bundle_roles,
		"added_roles": added_roles,
		"already_present_roles": [role for role in bundle_roles if role not in added_roles],
	}


def validate_bundle_management_access(user: str | None = None) -> None:
	can_manage_role_bundles(user, raise_exception=True)


def _get_current_user() -> str | None:
	try:
		return getattr(frappe.session, "user", None)
	except RuntimeError:
		return None
