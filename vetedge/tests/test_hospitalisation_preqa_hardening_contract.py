from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks.py"
SECURITY = ROOT / "services" / "hospitalisation_preqa_security.py"
OPERATIONS_PAGE = (
    ROOT
    / "veterinary"
    / "page"
    / "vetedge_hospitalisation_operations"
    / "vetedge_hospitalisation_operations.js"
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_hospitalisation_operations_failed_drillthrough_is_hardened_in_place():
    page = read(OPERATIONS_PAGE)
    security = read(SECURITY)

    assert "HOSPITALISATION_PATIENT_SNAPSHOT_API" in page
    assert "get_hospitalisation_patient_snapshot" in page
    assert "showHospitalisationPatientSnapshot(event.row)" in page
    assert "if (field === 'branch') return;" in page
    assert "openHospitalisationEpisodeRoute(event.row.hospitalisation)" in page
    assert "Patient & Pet Owner" in page
    assert "Customer ID" in page
    assert "Mobile" in page
    assert "Email" in page

    # Snapshot identity is derived only after the referenced Hospitalisation has
    # passed normal DocType and fail-closed Branch checks.
    assert "doc = _load_hospitalisation(hospitalisation_name, write=False)" in security
    assert '"patient": patient' in security
    assert '"owner": owner' in security


def test_operations_branch_column_is_informational_not_a_link():
    hooks = read(HOOKS)
    security = read(SECURITY)

    assert (
        '"vetedge.services.hospitalisation_operations.get_hospitalisation_operations": '
        '"vetedge.services.hospitalisation_preqa_security.get_hospitalisation_operations"'
    ) in hooks
    assert 'if column.get("fieldname") == "branch":' in security
    assert 'column["fieldtype"] = "Data"' in security
    assert 'column.pop("options", None)' in security
    assert 'column["clickable"] = False' in security


def test_legacy_hospitalisation_rpc_paths_are_permission_and_branch_guarded():
    hooks = read(HOOKS)
    security = read(SECURITY)

    guarded_methods = (
        "get_hospitalisation_patient_context",
        "create_hospitalisation_from_consultation",
        "get_hospitalisation_medication_item_context",
        "build_hospitalisation_charge_items",
        "create_or_link_hospitalisation_invoice",
        "sync_hospitalisation_charges_to_invoice",
        "assign_hospitalisation_care_location",
        "release_hospitalisation_care_location",
        "get_available_care_locations",
    )
    for method in guarded_methods:
        assert (
            f'"vetedge.services.hospitalisation.{method}": '
            f'"vetedge.services.hospitalisation_preqa_security.{method}"'
        ) in hooks

    for expected in (
        "doc.check_permission(\"write\" if write else \"read\")",
        "validate_hospitalisation_branch_access(doc)",
        "get_assigned_branches(user)",
        "user_has_global_branch_access(user)",
        "You do not have an assigned Veterinary Branch",
        "consultation.check_permission(\"read\")",
        "_assert_branch_visible(consultation.get(\"service_branch\"))",
    ):
        assert expected in security

    assert "ignore_permissions" not in security


def test_care_location_legacy_picker_cannot_enumerate_other_branches():
    security = read(SECURITY)

    assert "if requested_branch:" in security
    assert "_assert_branch_visible(requested_branch)" in security
    assert "for allowed_branch in allowed:" in security
    assert "original(branch=allowed_branch" in security
    assert "Care Location Branch must match the Hospitalisation Branch" in security
