import json
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
SERVICE = APP_ROOT / "services" / "care_location_workspace.py"
DOCTYPE_JSON = (
    APP_ROOT
    / "veterinary"
    / "doctype"
    / "veterinary_care_location"
    / "veterinary_care_location.json"
)


def test_care_location_name_is_document_identity_and_is_renamed_safely():
    meta = json.loads(DOCTYPE_JSON.read_text(encoding="utf-8"))
    source = SERVICE.read_text(encoding="utf-8")

    assert meta.get("autoname") == "field:location_name"
    assert meta.get("allow_rename") == 1
    assert "_rename_care_location_if_needed" in source
    assert "frappe.rename_doc(" in source
    assert "merge=False" in source
    assert "show_alert=False" in source
    assert "return frappe.get_doc(DOCTYPE, new_name)" in source
    assert 'doc = _rename_care_location_if_needed(doc, payload["location_name"])' in source


def test_care_location_rename_rejects_duplicate_target_names():
    source = SERVICE.read_text(encoding="utf-8")

    assert "frappe.db.exists(DOCTYPE, requested_name)" in source
    assert "frappe.DuplicateEntryError" in source
