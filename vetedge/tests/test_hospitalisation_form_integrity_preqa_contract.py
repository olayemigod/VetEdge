from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORM_POLICY = ROOT / "services" / "hospitalisation_form_integrity.py"
FALLBACK_JS = ROOT / "public" / "js" / "vetedge_hospitalisation_preqa.js"
CONTROLLER = (
    ROOT
    / "veterinary"
    / "doctype"
    / "veterinary_hospitalisation"
    / "veterinary_hospitalisation.py"
)
HOOKS = ROOT / "hooks.py"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_native_hospitalisation_form_uses_branch_aware_practitioner_policy():
    policy = read(FORM_POLICY)
    client = read(FALLBACK_JS)
    hooks = read(HOOKS)

    assert 'ASSIGNMENT_DOCTYPE = "Branch Practitioner Assignment"' in policy
    assert "_assignment_policy_enabled(branch)" in policy
    assert '"branch": branch, "practitioner": practitioner, "disabled": 0' in policy
    assert "search_hospitalisation_practitioners" in policy
    assert "Attending Veterinarian {0} is not assigned to Veterinary Branch {1}." in policy
    assert "search_hospitalisation_practitioners" in client
    assert "is_hospitalisation_practitioner_allowed" in client
    assert 'filters: { branch: frm.doc.service_branch || "" }' in client
    assert (
        '"vetedge.services.hospitalisation_episode.search_hospitalisation_episode_options": '
        '"vetedge.services.hospitalisation_form_integrity.search_hospitalisation_episode_options"'
    ) in hooks


def test_native_hospitalisation_care_location_cannot_bypass_occupancy_actions():
    policy = read(FORM_POLICY)
    client = read(FALLBACK_JS)

    assert "_care_location_change_is_managed" in policy
    assert "Use Assign Care Location or Release Care Location" in policy
    assert 'BLOCKED_CARE_LOCATION_STATUSES = {"Inactive", "Maintenance", "Cleaning"}' in policy
    assert '"capacity"' in policy
    assert "get_active_care_location_occupancy_count" in policy
    assert "Selected Care Location is already full." in policy
    assert 'frm.set_df_property("care_location", "read_only", 1)' in client
    assert "occupancy history and capacity remain accurate" in client


def test_native_hospitalisation_activity_edits_match_episode_item_safety():
    policy = read(FORM_POLICY)

    assert "ITEM_REQUIRED_ACTIVITY_TYPES" in policy
    assert "_changed_activity_rows" in policy
    assert "_validate_activity_item" in policy
    assert "is_hospitalisation_dispensary_enabled" in policy
    assert 'row.stock_status = "Not Applicable"' in policy
    assert "ERPNext Item is required for billable, stock-affecting, Medication and Fluid Therapy" in policy
    assert "Hospitalisation activity quantity must be greater than zero." in policy


def test_hospitalisation_controller_runs_fallback_integrity_before_main_validation():
    controller = read(CONTROLLER)

    assert "from vetedge.services.hospitalisation_form_integrity import enforce_hospitalisation_form_integrity" in controller
    assert "enforce_hospitalisation_form_integrity(self)" in controller
    assert controller.index("enforce_hospitalisation_form_integrity(self)") < controller.index("validate_hospitalisation(self)")
