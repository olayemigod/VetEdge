from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_hospitalisation_participates_in_shared_save_integrity():
    branch_source = (ROOT / "services/branch_integrity.py").read_text(encoding="utf-8")
    practitioner_source = (ROOT / "services/practitioner_integrity.py").read_text(encoding="utf-8")
    controller = (
        ROOT / "veterinary/doctype/veterinary_hospitalisation/veterinary_hospitalisation.py"
    ).read_text(encoding="utf-8")

    assert '"Veterinary Hospitalisation": "service_branch"' in branch_source
    assert '"Veterinary Hospitalisation": "attending_veterinarian"' in practitioner_source
    assert 'if doc.doctype == "Veterinary Hospitalisation":' in practitioner_source
    assert "enforce_branch_integrity(self)" in controller
    assert "enforce_practitioner_integrity(self)" in controller
    assert 'validate_doctor_user(self.attending_veterinarian, label="Attending Veterinarian")' in controller
    assert "validate_hospitalisation(self)" in controller


def test_deceased_patient_guard_covers_hospitalisation_delivery_transitions():
    source = (ROOT / "services/patient_service_guard.py").read_text(encoding="utf-8")
    assert '"Veterinary Hospitalisation": {"Admitted", "Under Care", "Ready for Discharge"}' in source


def test_hospitalisation_read_permissions_are_branch_scoped_and_fail_closed():
    permissions = (ROOT / "services/hospitalisation_permissions.py").read_text(encoding="utf-8")
    hooks = (ROOT / "hooks.py").read_text(encoding="utf-8")

    for expected in (
        'return "1=0"',
        "get_assigned_branches(user)",
        "user_has_global_branch_access(user)",
        "is_internal_staff_user(user)",
        "is_portal_owner_user(user)",
        'BRANCH_FIELD = "service_branch"',
        "branch in allowed",
    ):
        assert expected in permissions

    assert (
        '"Veterinary Hospitalisation": '
        '"vetedge.services.hospitalisation_permissions.get_hospitalisation_query"'
    ) in hooks
    assert (
        '"Veterinary Hospitalisation": '
        '"vetedge.services.hospitalisation_permissions.has_hospitalisation_permission"'
    ) in hooks
    assert "ignore_permissions" not in permissions


def test_retired_hospitalisation_dashboard_is_filtered_at_runtime():
    source = (ROOT / "install/dashboard.py").read_text(encoding="utf-8")
    assert '"veterinary-hospitalisation-dashboard"' in source
    assert "REMOVED_STANDARD_PAGES" in source
    assert "REMOVED_SIDEBAR_LINKS" in source
    assert "_should_keep_sidebar_item" in source
