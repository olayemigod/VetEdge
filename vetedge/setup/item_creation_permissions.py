from __future__ import annotations

import frappe

ITEM_DOCTYPE = "Item"
DOCTOR_ROLE = "VetEdge Doctor"
STOCK_USER_ROLE = "Stock User"
MANAGED_CREATOR_ROLE = "VetEdge Clinical Item Creator"
SYSTEM_MANAGER_ROLE = "System Manager"
SOURCE_ROLES = {DOCTOR_ROLE, STOCK_USER_ROLE}


def user_is_doctor_stock_user(roles) -> bool:
	return SOURCE_ROLES.issubset(set(roles or []))


def reconcile_user_item_creator_role(doc, method=None) -> bool:
	"""Keep the managed creator role equal to Doctor AND Stock User."""
	if getattr(doc, "doctype", None) != "User":
		return False

	rows = list(doc.get("roles") or [])
	roles = {row.get("role") for row in rows if row.get("role")}
	should_have = user_is_doctor_stock_user(roles)
	has_managed_role = MANAGED_CREATOR_ROLE in roles

	if should_have and not has_managed_role:
		doc.append("roles", {"role": MANAGED_CREATOR_ROLE})
		return True
	if not should_have and has_managed_role:
		doc.set("roles", [row for row in rows if row.get("role") != MANAGED_CREATOR_ROLE])
		return True
	return False


def ensure_item_create_permission() -> bool:
	"""Grant create-only Item permission through Frappe's supported custom layer."""
	if not frappe.db.exists("DocType", ITEM_DOCTYPE):
		return False

	# setup_custom_perms preserves the current ERPNext Item permission matrix when
	# a site has not customized it yet. Existing custom permissions are retained.
	from frappe.permissions import setup_custom_perms

	setup_custom_perms(ITEM_DOCTYPE)
	permission_doctype = "Custom DocPerm"
	filters = {
		"parent": ITEM_DOCTYPE,
		"role": MANAGED_CREATOR_ROLE,
		"permlevel": 0,
		"if_owner": 0,
	}
	name = frappe.db.get_value(permission_doctype, filters, "name")
	if name:
		if not frappe.db.get_value(permission_doctype, name, "create"):
			frappe.db.set_value(permission_doctype, name, "create", 1, update_modified=False)
			frappe.clear_cache(doctype=ITEM_DOCTYPE)
			return True
		return False

	frappe.get_doc(
		{
			"doctype": permission_doctype,
			"parent": ITEM_DOCTYPE,
			"parenttype": "DocType",
			"parentfield": "permissions",
			"role": MANAGED_CREATOR_ROLE,
			"permlevel": 0,
			"if_owner": 0,
			"create": 1,
		}
	).insert(ignore_permissions=True)
	frappe.clear_cache(doctype=ITEM_DOCTYPE)
	return True


def reconcile_existing_doctor_stock_users() -> int:
	if not frappe.db.exists("DocType", "Has Role"):
		return 0

	users = set(
		frappe.get_all(
			"Has Role",
			filters={"parenttype": "User", "role": ["in", [*SOURCE_ROLES, MANAGED_CREATOR_ROLE]]},
			pluck="parent",
		)
	)
	changed = 0
	for user in sorted(filter(None, users)):
		if not frappe.db.exists("User", user):
			continue
		user_doc = frappe.get_doc("User", user)
		if reconcile_user_item_creator_role(user_doc):
			user_doc.save(ignore_permissions=True)
			changed += 1
	return changed


def ensure_doctor_stock_item_creation() -> None:
	ensure_item_create_permission()
	reconcile_existing_doctor_stock_users()


def has_item_permission(doc, user=None, permission_type=None, ptype=None, **kwargs) -> bool:
	"""Fail closed if the managed role exists without both qualifying roles.

	Frappe controller hooks can deny but cannot grant. The managed DocPerm grants
	create access; this hook enforces the source-role conjunction server-side.
	"""
	requested_permission = permission_type or ptype
	if requested_permission != "create":
		return True

	user = user or getattr(frappe.session, "user", None)
	roles = set(frappe.get_roles(user) or [])
	if SYSTEM_MANAGER_ROLE in roles or MANAGED_CREATOR_ROLE not in roles:
		return True
	return user_is_doctor_stock_user(roles)
