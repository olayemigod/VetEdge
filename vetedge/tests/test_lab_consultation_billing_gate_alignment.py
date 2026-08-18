from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_consultation_lab_gate_requires_lab_specific_billing_evidence_before_using_consultation_gate():
    context = read(APP / "services/lab_billing_context.py")

    assert 'f"consultation-plan::Lab Order::{doc.name}::{detail}"' in context
    assert '"source_doctype": CONSULTATION_DOCTYPE' in context
    assert '"source_name": consultation' in context
    assert '"source_doctype": LAB_ORDER_DOCTYPE' in context
    assert '"source_name": doc.name' in context
    assert 'evidence.get("docstatus") not in {0, 1}' in context
    assert 'get_source_payment_gate_status(CONSULTATION_DOCTYPE, consultation)' in context
    assert '"lab_charge_coverage_complete": False' in context
    assert '"lab_charge_coverage_complete"] = True' in context
    assert "get_or_create_billing_session" not in context
    assert "sync_source_to_billing_session" not in context
    assert "ignore_permissions" not in context


def test_workflow_and_final_completion_use_the_same_aligned_lab_gate():
    workflow = read(APP / "services/lab_payment_workflow.py")
    lab = read(APP / "services/lab.py")

    assert "from vetedge.services.lab_billing_context import get_lab_billing_core_gate_state" in workflow
    assert "return get_lab_billing_core_gate_state(doc)" in workflow
    assert "from vetedge.services.lab_billing_context import get_lab_billing_core_gate_state" in lab
    assert "gate = get_lab_billing_core_gate_state(doc)" in lab

    completion = lab.split("def validate_lab_order_completion_gate", 1)[1].split("def lab_order_has_billable_items", 1)[0]
    assert "resolve_billing_session" not in completion
    assert "get_payment_gate_status" not in completion


def test_clinical_editor_replaces_stale_lab_row_billing_display_and_locks_submitted_prices():
    state = read(APP / "services/clinical_record_state.py")

    assert "def _apply_lab_billing_evidence(state: dict, gate: dict) -> None:" in state
    assert 'row["billing_status"] = evidence.get("billing_status")' in state
    assert 'row["billing_invoice"] = evidence.get("invoice")' in state
    assert 'row["can_edit_rate"] = False' in state
    assert "LAB_SAFE_AFTER_SUBMITTED_INVOICE = {\"sample_notes\"}" in state
    assert 'field["read_only"] = 1' in state
    assert "_apply_lab_billing_evidence(state, gate)" in state
