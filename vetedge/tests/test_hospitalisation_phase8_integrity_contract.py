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
    assert "resolve_hospitalisation_context(self)" in controller
    assert "enforce_branch_integrity(self)" in controller
    assert "validate_hospitalisation_branch_access(self)" in controller
    assert "enforce_practitioner_integrity(self)" in controller
    assert 'validate_doctor_user(self.attending_veterinarian, label="Attending Veterinarian")' in controller
    assert "validate_hospitalisation(self)" in controller


def test_hospitalisation_context_uses_patient_default_branch_only_as_fallback():
    source = (ROOT / "services/hospitalisation_context.py").read_text(encoding="utf-8")

    for expected in (
        '"primary_owner", "default_branch"',
        '_set_if_missing(doc, "service_branch", patient.get("default_branch"))',
        '_require_same(_("Patient"), doc.get("patient"), consultation.get("patient"))',
        '_require_same(_("Pet Owner"), doc.get("customer"), consultation.get("primary_owner"))',
        '_require_same(_("Service Branch"), doc.get("service_branch"), consultation.get("service_branch"))',
        '_require_same(_("Company"), doc.get("company"), consultation.get("company"))',
        "_is_unchanged_historical_owner",
        "current Primary Owner",
        "Consultation preserves the owner for that clinical episode",
    ):
        assert expected in source

    assert "patient.default_branch !=" not in source
    assert "default_branch ==" not in source
    assert "Linked Consultation Owner does not match the selected Patient's Primary Owner" not in source


def test_deceased_patient_guard_covers_hospitalisation_delivery_transitions():
    source = (ROOT / "services/patient_service_guard.py").read_text(encoding="utf-8")
    assert '"Veterinary Hospitalisation": {"Admitted", "Under Care", "Ready for Discharge"}' in source


def test_hospitalisation_read_and_save_permissions_are_branch_scoped_and_fail_closed():
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
        "validate_hospitalisation_branch_access",
        "You do not have an assigned Veterinary Branch",
        "You do not have access to the selected Hospitalisation Branch",
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
