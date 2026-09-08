from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
	return (APP_ROOT / relative_path).read_text(encoding="utf-8")


def test_shared_host_boot_uses_module_label_for_all_launchers():
	adapter = read("coreedge_adapter.py")

	assert 'launcher_label = branding.get("module_label") or "Veterinary"' in adapter
	assert 'icon["label"] = launcher_label' in adapter
	assert 'app["app_title"] = launcher_label' in adapter
	assert 'bootinfo.app_title = branding.get("app_title")' in adapter


def test_production_sites_receive_launcher_cache_migration():
	patches = read("patches.txt")
	patch = read("patches/normalize_veterinary_launcher_boot_label.py")

	assert "vetedge.patches.normalize_veterinary_launcher_boot_label" in patches
	assert 'frappe.cache.delete_key("desktop_icons")' in patch
	assert 'frappe.cache.delete_key("bootinfo")' in patch


def test_item_creation_requires_managed_doctor_and_stock_user_contract():
	hooks = read("hooks.py")
	setup = read("setup/item_creation_permissions.py")
	installer = read("install/__init__.py")

	assert '"Item": "vetedge.setup.item_creation_permissions.has_item_permission"' in hooks
	assert '"before_save": "vetedge.setup.item_creation_permissions.reconcile_user_item_creator_role"' in hooks
	assert 'SOURCE_ROLES = {DOCTOR_ROLE, STOCK_USER_ROLE}' in setup
	assert "return SOURCE_ROLES.issubset(set(roles or []))" in setup
	assert "from frappe.permissions import setup_custom_perms" in setup
	assert "setup_custom_perms(ITEM_DOCTYPE)" in setup
	assert 'permission_doctype = "Custom DocPerm"' in setup
	assert '"create": 1' in setup
	assert "MANAGED_CREATOR_ROLE not in roles" in setup
	assert "ensure_doctor_stock_item_creation()" in installer
