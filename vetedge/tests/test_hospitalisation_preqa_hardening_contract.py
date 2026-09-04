from __future__ import annotations

import json
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
EPISODE_VUE = ROOT / "public" / "js" / "vetedge_hospitalisation_episode" / "VetEdgeHospitalisationEpisode.vue"
CARE_LOCATION = (
    ROOT
    / "veterinary"
    / "doctype"
    / "veterinary_care_location"
    / "veterinary_care_location.json"
)
OCCUPANCY_LOG = (
    ROOT
    / "veterinary"
    / "doctype"
    / "veterinary_care_location_occupancy_log"
    / "veterinary_care_location_occupancy_log.json"
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def role_permissions(path: Path, role: str) -> list[dict]:
    data = json.loads(read(path))
    return [row for row in data.get("permissions") or [] if row.get("role") == role]


def test_hospitalisation_operations_failed_drillthrough_is_hardened_in_place():
    page = read(OPERATIONS_PAGE)
    security = read(SECURITY)

    assert "HOSPITALISATION_PATIENT_SNAPSHOT_API" in page
    assert "get_hospitalisation_patient_snapshot" in page
    assert "showHospitalisationPatientSnapshot(event.row)" in page
    assert "field === 'patient_name' || field === 'owner'" in page
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


def test_care_location_workflow_owns_audit_mutation_without_granting_doctor_crud():
    security = read(SECURITY)

    # The caller must pass the normal Hospitalisation write/Branch boundary
    # before the narrowly-scoped system-maintained Care Location records use
    # elevated persistence.
    assert "doc = _load_hospitalisation(hospitalisation_name, write=True)" in security
    assert "_assert_not_stale(doc, modified)" in security
    assert "service.ensure_care_location_assignable(doc, location)" in security
    assert "ACTIVE_CARE_LOCATION_HOSPITALISATION_STATUSES" in security
    assert "log.insert(ignore_permissions=True)" in security
    assert "log.save(ignore_permissions=True)" in security
    assert "location.save(ignore_permissions=True)" in security

    # Ordinary Doctors still do not receive broad master/audit permissions.
    assert role_permissions(CARE_LOCATION, "VetEdge Doctor") == []
    assert role_permissions(OCCUPANCY_LOG, "VetEdge Doctor") == []


def test_care_location_legacy_picker_cannot_enumerate_other_branches():
    security = read(SECURITY)

    assert "if requested_branch:" in security
    assert "_assert_branch_visible(requested_branch)" in security
    assert "for allowed_branch in allowed:" in security
    assert "original(branch=allowed_branch" in security
    # Assignment itself delegates the final location/Branch/capacity check to
    # the existing authoritative Hospitalisation service after the caller has
    # already passed the Hospitalisation Branch boundary.
    assert "service.ensure_care_location_assignable(doc, location)" in security


def test_linked_clinical_record_snapshot_is_bounded_and_episode_authorised():
    page = read(OPERATIONS_PAGE)
    security = read(SECURITY)

    assert "HOSPITALISATION_LINKED_RECORD_SNAPSHOT_API" in page
    assert "get_hospitalisation_linked_record_snapshot" in page
    assert "view.openDocument = (doctype, name) => showHospitalisationLinkedRecordSnapshot" in page
    assert "LINKED_RECORD_FIELDS" in security
    assert '"Veterinary Vital Signs"' in security
    assert '"Veterinary Vaccination Record"' in security
    assert '"Veterinary Lab Order"' in security
    assert "linked_from_episode = any(" in security
    assert "record.check_permission(\"read\")" in security
    assert "The requested clinical record is not linked to this Hospitalisation" in security


def test_hosted_episode_care_location_uses_authorised_workflow_api():
    page = read(OPERATIONS_PAGE)

    assert "HOSPITALISATION_ASSIGN_CARE_LOCATION_API" in page
    assert "HOSPITALISATION_RELEASE_CARE_LOCATION_API" in page
    assert "['assign_location', 'release_location'].includes(action)" in page
    assert "modified: view.episode.modified" in page


def test_hospitalisation_vaccination_preserves_next_due_datetime():
    episode = read(EPISODE_VUE)

    assert 'vaccinationDialog.values.next_due_date" type="datetime-local" label="Next Due Date/Time"' in episode
    assert "next_due_date: serverDatetime(this.vaccinationDialog.values.next_due_date)" in episode
    assert 'vaccinationDialog.values.next_due_date" type="date"' not in episode
