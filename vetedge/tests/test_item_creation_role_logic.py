from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

MODULE_PATH = Path(__file__).resolve().parents[1] / "setup" / "item_creation_permissions.py"


def load_module():
	frappe_stub = SimpleNamespace(
		session=SimpleNamespace(user="doctor@example.com"),
		get_roles=lambda user=None: [],
	)
	previous = sys.modules.get("frappe")
	sys.modules["frappe"] = frappe_stub
	try:
		spec = importlib.util.spec_from_file_location("vetedge_item_creation_permissions_test", MODULE_PATH)
		module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(module)
	finally:
		if previous is None:
			sys.modules.pop("frappe", None)
		else:
			sys.modules["frappe"] = previous
	return module, frappe_stub


class FakeUser:
	doctype = "User"

	def __init__(self, roles):
		self.roles = [{"role": role} for role in roles]

	def get(self, fieldname):
		return getattr(self, fieldname)

	def append(self, fieldname, value):
		getattr(self, fieldname).append(value)

	def set(self, fieldname, value):
		setattr(self, fieldname, value)


def role_names(user):
	return {row["role"] for row in user.roles}


def test_managed_role_is_added_only_for_doctor_and_stock_user():
	module, _frappe = load_module()
	eligible = FakeUser([module.DOCTOR_ROLE, module.STOCK_USER_ROLE])
	doctor_only = FakeUser([module.DOCTOR_ROLE])

	assert module.reconcile_user_item_creator_role(eligible) is True
	assert module.MANAGED_CREATOR_ROLE in role_names(eligible)
	assert module.reconcile_user_item_creator_role(doctor_only) is False
	assert module.MANAGED_CREATOR_ROLE not in role_names(doctor_only)


def test_managed_role_is_removed_when_stock_user_role_is_removed():
	module, _frappe = load_module()
	user = FakeUser([module.DOCTOR_ROLE, module.MANAGED_CREATOR_ROLE])

	assert module.reconcile_user_item_creator_role(user) is True
	assert role_names(user) == {module.DOCTOR_ROLE}


def test_server_permission_fails_closed_for_stale_managed_role():
	module, frappe_stub = load_module()
	frappe_stub.get_roles = lambda user=None: [module.DOCTOR_ROLE, module.MANAGED_CREATOR_ROLE]

	assert module.has_item_permission(None, permission_type="create") is False

	frappe_stub.get_roles = lambda user=None: [
		module.DOCTOR_ROLE,
		module.STOCK_USER_ROLE,
		module.MANAGED_CREATOR_ROLE,
	]
	assert module.has_item_permission(None, permission_type="create") is True


def test_item_hook_does_not_replace_native_non_create_permissions():
	module, frappe_stub = load_module()
	frappe_stub.get_roles = lambda user=None: [module.DOCTOR_ROLE]

	assert module.has_item_permission(None, permission_type="read") is True
	assert module.has_item_permission(None, permission_type="write") is True
