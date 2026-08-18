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


def test_retired_hospitalisation_dashboard_is_filtered_at_runtime():
    source = (ROOT / "install/dashboard.py").read_text(encoding="utf-8")
    assert '"veterinary-hospitalisation-dashboard"' in source
    assert "REMOVED_STANDARD_PAGES" in source
    assert "REMOVED_SIDEBAR_LINKS" in source
    assert "_should_keep_sidebar_item" in source
