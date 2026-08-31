import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DESKTOP_ICON = ROOT / "vetedge" / "desktop_icon" / "vetedge.json"
PATCHES = ROOT / "vetedge" / "patches.txt"
MIGRATION = ROOT / "vetedge" / "patches" / "normalize_veterinary_desktop_icon_label.py"


def test_visible_desk_icon_is_veterinary_without_renaming_internal_identity():
	payload = json.loads(DESKTOP_ICON.read_text(encoding="utf-8"))

	assert payload["app"] == "vetedge"
	assert payload["name"] == "VetEdge"
	assert payload["link_to"] == "VetEdge"
	assert payload["label"] == "Veterinary"


def test_existing_sites_receive_idempotent_visible_label_migration():
	patches = PATCHES.read_text(encoding="utf-8")
	migration = MIGRATION.read_text(encoding="utf-8")

	assert "vetedge.patches.normalize_veterinary_desktop_icon_label" in patches
	assert 'for icon_name in ("VetEdge", "Veterinary")' in migration
	assert '"label",\n\t\t\t\t"Veterinary"' in migration
	assert "update_modified=False" in migration
