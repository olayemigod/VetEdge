from pathlib import Path


def test_clinical_modal_workflow_contract_files_exist():
    root = Path(__file__).resolve().parents[2]
    assert (root / "vetedge/public/js/billing_modal.js").exists()
    assert (root / "vetedge/services/consultation_cancellation.py").exists()
