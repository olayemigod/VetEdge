from __future__ import annotations

import frappe
from frappe.utils import cint

from vetedge.services.audit import log_operational_event
from vetedge.services.permissions import can_apply_role_bundle, can_manage_role_bundles


STARTER_ROLE_BUNDLES = {
	"VetEdge Administrator": [
		"VetEdge Administrator",
		"Desk User",
		"Workspace Manager",
		"Report Manager",
		"Accounts User",
		"Sales User",
		"Stock User",
	],
	"Veterinary Doctor": [
		"VetEdge Doctor",
		"Desk User",
		"Sales User",
		"Stock User",
	],
	"Veterinary Nurse": [
		"Veterinary Nurse",
		"Desk User",
		"Stock User",
	],
	"Front Desk": [
		"VetEdge Front Desk",
		"Desk User",
		"Sales User",
	],
	"Dispensary User": [
		"Dispensary User",
		"Desk User",
		"Stock User",
		"Sales User",
	],
	"Lab Technician": [
		"Lab Technician",
		"Desk User",
		"Stock User",
	],
	"Branch Manager": [
		"Branch Manager",
		"Desk User",
		"Accounts User",
		"Sales User",
		"Stock User",
	],
	"Accounts/Cashier": [
		"Accounts/Cashier",
		"Desk User",
		"Accounts User",
		"Sales User",
	],
}


def ensure_starter_role_bundles() -> None:
	if not frappe.db.exists("DocType", "VetEdge Role Bundle"):
		return

	for bundle_name, roles in STARTER_ROLE_BUNDLES.items():
		if frappe.db.exists("VetEdge Role Bundle", bundle_name):
			bundle = frappe.get_doc("VetEdge Role Bundle", bundle_name)
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
				"doctype": "VetEdge Role Bundle",
				"bundle_name": bundle_name,
				"is_active": 1,
				"roles": [{"role": role} for role in roles],
			}
		)
		bundle.insert(ignore_permissions=True)


@frappe.whitelist()
def apply_role_bundle_to_user(bundle_name: str, target_user: str) -> dict:
	return apply_role_bundle(bundle_name, target_user)


def apply_role_bundle(bundle_name: str, target_user: str, acting_user: str | None = None) -> dict:
	acting_user = acting_user or _get_current_user()
	can_apply_role_bundle(acting_user, target_user, raise_exception=True)

	if not frappe.db.exists("User", target_user):
		frappe.throw("Target user must be a valid User.", frappe.ValidationError)

	bundle = frappe.get_doc("VetEdge Role Bundle", bundle_name)
	if cint(getattr(bundle, "is_active", 1)) != 1:
		frappe.throw("Only active role bundles can be applied.", frappe.ValidationError)

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
