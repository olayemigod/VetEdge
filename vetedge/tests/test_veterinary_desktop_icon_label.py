import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DESKTOP_ICON = ROOT / "vetedge" / "desktop_icon" / "vetedge.json"
HOOKS = ROOT / "vetedge" / "hooks.py"
PATCHES = ROOT / "vetedge" / "patches.txt"
MIGRATION = ROOT / "vetedge" / "patches" / "normalize_veterinary_desktop_icon_label.py"
LAYOUT_MIGRATION = ROOT / "vetedge" / "patches" / "normalize_veterinary_desktop_layout_labels.py"
LAYOUT_LINK_MIGRATION = (
	ROOT / "vetedge" / "patches" / "normalize_veterinary_desktop_layout_link_labels.py"
)
ALL_USERS_MIGRATION = (
	ROOT / "vetedge" / "patches" / "normalize_veterinary_desktop_icon_all_users.py"
)


def test_visible_desk_icon_is_veterinary_without_renaming_internal_identity():
	payload = json.loads(DESKTOP_ICON.read_text(encoding="utf-8"))

	assert payload["app"] == "vetedge"
	assert payload["name"] == "VetEdge"
	assert payload["link_to"] == "VetEdge"
	assert payload["label"] == "Veterinary"


def test_apps_screen_launcher_is_veterinary_without_renaming_app_identity():
	hooks = HOOKS.read_text(encoding="utf-8")

	assert 'app_name = "vetedge"' in hooks
	assert 'app_title = "VetEdge"' in hooks
	assert '"name": app_name' in hooks
	assert '"title": "Veterinary"' in hooks
	assert '"route": app_home' in hooks
	assert '"title": app_title' not in hooks


def test_existing_sites_receive_idempotent_visible_label_migration():
	patches = PATCHES.read_text(encoding="utf-8")
	migration = MIGRATION.read_text(encoding="utf-8")

	assert "vetedge.patches.normalize_veterinary_desktop_icon_label" in patches
	assert 'for icon_name in ("VetEdge", "Veterinary")' in migration
	assert '"label",\n\t\t\t\t"Veterinary"' in migration
	assert "update_modified=False" in migration


def test_saved_desktop_layout_snapshots_are_normalized_without_resetting_user_layouts():
	patches = PATCHES.read_text(encoding="utf-8")
	migration = LAYOUT_MIGRATION.read_text(encoding="utf-8")
	old_patch = "vetedge.patches.normalize_veterinary_desktop_icon_label"
	layout_patch = "vetedge.patches.normalize_veterinary_desktop_layout_labels"

	assert layout_patch in patches
	assert patches.index(old_patch) < patches.index(layout_patch)
	assert 'frappe.db.exists("DocType", "Desktop Layout")' in migration
	assert 'frappe.get_all("Desktop Layout", fields=["name", "layout"])' in migration
	assert 'value.get("app") == APP_NAME' in migration
	assert 'value.get("parent_icon") == OLD_LABEL' in migration
	assert "json.loads" in migration
	assert "json.dumps" in migration
	assert "update_modified=False" in migration
	assert "delete_doc" not in migration


def test_frappe_v16_link_tile_layout_receives_forward_only_repair():
	patches = PATCHES.read_text(encoding="utf-8")
	migration = LAYOUT_LINK_MIGRATION.read_text(encoding="utf-8")
	v1_patch = "vetedge.patches.normalize_veterinary_desktop_layout_labels"
	v2_patch = "vetedge.patches.normalize_veterinary_desktop_layout_link_labels"

	assert v2_patch in patches
	assert patches.index(v1_patch) < patches.index(v2_patch)
	assert 'frappe.get_all("Desktop Layout", fields=["name", "user", "layout"])' in migration
	assert 'value.get("app") == APP_NAME' in migration
	assert 'value.get("name") == OLD_LABEL' in migration
	assert 'value.get("link_to") == OLD_LABEL' in migration
	assert 'value.get("label") == OLD_LABEL' in migration
	assert 'value["label"] = NEW_LABEL' in migration
	assert 'value.get("icon_type") == "App"' not in migration
	assert 'value.get("parent_icon") == OLD_LABEL' in migration
	assert "clear_desktop_icons_cache(user=user)" in migration
	assert "json.loads" in migration
	assert "json.dumps" in migration
	assert "update_modified=False" in migration
	assert "delete_doc" not in migration


def test_all_users_receive_forward_only_desktop_cache_repair():
	patches = PATCHES.read_text(encoding="utf-8")
	migration = ALL_USERS_MIGRATION.read_text(encoding="utf-8")
	previous_patch = "vetedge.patches.normalize_veterinary_desktop_layout_link_labels"
	all_users_patch = "vetedge.patches.normalize_veterinary_desktop_icon_all_users"

	assert all_users_patch in patches
	assert patches.index(previous_patch) < patches.index(all_users_patch)
	assert 'filters={"app": APP_NAME, "standard": 1}' in migration
	assert 'icon.link_type != "Workspace Sidebar"' in migration
	assert 'icon.icon_type != "Link"' in migration
	assert "icon.link_to != OLD_LABEL" in migration
	assert 'frappe.get_all("Desktop Layout", fields=["name", "user", "layout"])' in migration
	assert 'frappe.cache.delete_key("desktop_icons")' in migration
	assert 'frappe.cache.delete_key("bootinfo")' in migration
	assert "update_modified=False" in migration
	assert "rename_doc" not in migration
	assert "delete_doc" not in migration
