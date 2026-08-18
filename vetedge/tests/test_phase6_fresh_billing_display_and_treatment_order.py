from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return ROOT.joinpath(relative_path).read_text(encoding="utf-8")


def test_clinical_workspace_keeps_newest_treatment_addition_first():
    content = read("vetedge/veterinary/page/vetedge_clinical_workspace/vetedge_clinical_workspace.js")

    assert "function installNewestTreatmentFirst(component)" in content
    assert "const original = methods.addTreatment" in content
    assert "const newest = rows.pop();" in content
    assert "rows.unshift(newest);" in content
    assert "installNewestTreatmentFirst(window.VetEdgeClinicalWorkspace);" in content
    assert content.index("installNewestTreatmentFirst(window.VetEdgeClinicalWorkspace);") < content.index(
        "window.mountVetEdgeClinicalWorkspace(root[0])"
    )


def test_billing_response_never_labels_submitted_invoice_as_draft():
    content = read("vetedge/services/billing_context_alignment.py")

    assert "def _normalize_invoice_row_lifecycle(row: dict | None)" in content
    assert 'if docstatus == 1 or row.get("is_submitted"):' in content
    assert 'row["is_submitted"] = True' in content
    assert 'row["is_draft"] = False' in content
    assert 'if not status or status.lower() == "draft":' in content
    assert 'row["status"] = row.get("payment_status") or row.get("payment_state") or "Submitted"' in content
    assert "def _normalize_invoice_lifecycle_state(state: dict) -> dict:" in content
    assert "frappe.db.set_value" not in content
    assert "ignore_permissions" not in content
