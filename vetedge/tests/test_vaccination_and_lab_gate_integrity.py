from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text()


def test_vaccination_controller_routes_all_administration_validation_to_hardened_gate():
    source = _read("veterinary/doctype/veterinary_vaccination_record/veterinary_vaccination_record.py")

    assert "vaccination_service.enforce_vaccination_payment_before_administration" in source
    assert "enforce_vaccination_payment_before_administration" in source


def test_vaccination_gate_has_no_role_payment_bypass_and_requires_own_submitted_charge():
    source = _read("services/vaccination_payment_workflow.py")

    assert "PAYMENT_OVERRIDE_ROLES" not in source
    assert "user_has_any_role" not in source
    assert "source_invoice_submitted" in source
    assert 'gate": "Submitted Invoice Required"' in source
    assert "consultation-plan::Vaccination::" in source
    assert "Veterinary Vaccination Record:" in source


def test_consultation_linked_vaccination_uses_strict_consultation_gate():
    source = _read("services/vaccination_payment_workflow.py")

    assert "get_strict_source_payment_gate_status" in source
    assert "CONSULTATION_DOCTYPE" in source
    assert "linked_consultation" in source


def test_standalone_vaccination_preserves_vaccination_payment_policy():
    source = _read("services/vaccination_payment_workflow.py")

    assert "is_vaccination_payment_enforcement_enabled" in source
    assert "FULL_PAYMENT_REQUIRED" in source
    assert "NO_PAYMENT_GATE" in source
    assert "get_invoice_collection_payment_gate_status" in source


def test_vaccination_workflow_ui_uses_same_hardened_preflight():
    source = _read("services/clinical_workflow_ui.py")

    assert "get_vaccination_administration_gate_state" in source
    assert "payment_ready = bool(payment_state.get" in source
    assert '"billing_required": billing_required' in source


def test_strict_clinical_gate_blocks_pending_and_draft_active_billing_cycles():
    source = _read("services/clinical_payment_gate.py")

    assert 'ledger.get("has_pending_uninvoiced_charges")' in source
    assert 'ledger.get("has_active_draft_invoice")' in source
    assert "get_source_payment_gate_status" in source


def test_lab_billing_core_requires_each_lab_source_invoice_to_be_submitted():
    source = _read("services/lab_billing_context.py")

    assert "source_invoices_submitted" in source
    assert "unsubmitted_rows" in source
    assert 'gate": "Submitted Invoice Required"' in source
    assert "get_strict_source_payment_gate_status" in source


def test_lab_non_billing_core_fallback_applies_configured_payment_gate():
    source = _read("services/lab_payment_workflow.py")

    assert "evaluate_invoice_payment_gate" in source
    assert "get_consultation_payment_gate" in source
    assert "default_payment_gate_mode" in source


def test_lab_cancellation_blocks_result_and_financial_commitments_at_server_boundary():
    cancellation = _read("services/lab_cancellation.py")
    controller = _read("veterinary/doctype/veterinary_lab_order/veterinary_lab_order.py")

    assert "build_lab_order_cancellation_preflight" in cancellation
    assert "submitted invoice/payment evidence" in cancellation
    assert "draft billing" in cancellation
    assert "diagnostic result evidence" in cancellation
    assert "PROTECTED_PLAN_BILLING_STATUSES" in cancellation
    assert "PROTECTED_PLAN_PAYMENT_STATUSES" in cancellation
    assert "enforce_lab_order_cancellation" in controller
    assert "enforce_lab_order_delete" in controller
    assert "def on_trash" in controller


def test_lab_cancellation_never_uses_submitted_invoice_mutation_for_cleanup():
    cancellation = _read("services/lab_cancellation.py")

    assert 'if docstatus in {0, 1}:' in cancellation
    assert 'billing_status") in {"Submitted Invoiced", "Paid"}' in cancellation
    assert '"billing_status": "Cancelled"' in cancellation
    assert 'frappe.delete_doc("Sales Invoice"' not in cancellation
    assert ".cancel()" not in cancellation


def test_lab_workflow_ui_uses_same_cancellation_preflight_and_hides_unsafe_action():
    source = _read("services/clinical_workflow_ui.py")

    assert "build_lab_order_cancellation_preflight" in source
    assert 'target == "Cancelled" and not cancellation_state.get("can_cancel")' in source
    assert '"cancellation": cancellation_state' in source
    assert "Submitted invoices and payments are never changed by this action." in source
