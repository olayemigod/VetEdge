from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_one_canonical_billing_modal_is_shared_across_services():
    hooks = read(APP / "hooks.py")
    canonical = read(APP / "public/js/billing_modal.js")
    compatibility = read(APP / "public/js/vetedge_billing_edgesuite.bundle.js")
    resource_loader = read(APP / "veterinary/page/vetedge_resource_center/vetedge_resource_center.js")
    history_loader = read(APP / "veterinary/page/veterinary_medical_history/veterinary_medical_history.js")

    assert '"/assets/vetedge/js/billing_modal.js"' in hooks
    assert "window.vetedgeBillingModal" in canonical
    assert "vetedge.services.billing_modal.get_billing_modal_state" in canonical
    assert "must never replace window.vetedgeBillingModal" in compatibility
    assert "window.vetedgeBillingModal =" not in compatibility
    assert "vetedge_billing_edgesuite.bundle.js" not in resource_loader
    assert "vetedge_billing_edgesuite.bundle.js" not in history_loader


def test_shared_billing_server_supports_all_billable_service_sources_and_registration():
    service = read(APP / "services/billing_modal.py")
    for doctype in (
        "Veterinary Consultation",
        "Veterinary Lab Order",
        "Veterinary Vaccination Record",
        "Veterinary Patient",
        "Pet Grooming Session",
        "Pet Boarding Booking",
        "Veterinary Hospitalisation",
    ):
        assert f'"{doctype}"' in service
    for contract in (
        "create_or_update_modal_invoice",
        "submit_modal_invoice",
        "record_modal_invoice_payment",
        "assert_can_act_on_source",
        "can_access_branch_data",
        "require_vetedge_platform_access",
        'frappe.has_permission("Sales Invoice", "submit"',
        'frappe.has_permission("Payment Entry", "create"',
        'frappe.has_permission("Payment Entry", "submit"',
        "assert_invoice_is_linked_to_source_or_session",
    ):
        assert contract in service


def test_billing_action_visibility_uses_same_erpnext_permissions_as_mutations():
    hooks = read(APP / "hooks.py")
    security = read(APP / "services/billing_state_security.py")

    assert "billing_state_security.get_billing_modal_state" in hooks
    assert 'frappe.has_permission("Sales Invoice", "submit", doc=invoice)' in security
    assert 'frappe.has_permission("Payment Entry", "create")' in security
    assert 'frappe.has_permission("Payment Entry", "submit")' in security
    assert "can_submit_invoice" in security
    assert "can_pay_outstanding" in security
    assert "patient_outstanding_context" in security


def test_registration_has_standalone_shared_billing_and_payment_path():
    registration = read(APP / "services/registration_billing.py")
    patient_form = read(APP / "veterinary/doctype/veterinary_patient/veterinary_patient.js")
    bridge = read(APP / "public/js/vetedge_resource_center_clinical_bridge.js")
    hooks = read(APP / "hooks.py")

    for contract in (
        "create_manual_registration_invoice",
        "Awaiting Registration Payment",
        "Registration Paid",
        "validate_registration_payment_before_first_consultation",
        "update_registration_status_from_invoice",
        "update_registration_status_from_payment_entry",
    ):
        assert contract in registration
    assert 'window.vetedgeBillingModal.open(frm)' in patient_form
    assert "Registration Billing / Payment" in bridge
    assert 'billingFrame("Veterinary Patient"' in bridge
    assert "update_registration_status_from_invoice" in hooks
    assert "update_registration_status_from_payment_entry" in hooks


def test_lab_order_creation_uses_dropdown_picker_without_losing_multi_test_orders():
    picker = read(APP / "public/js/vetedge_lab_order_picker_patch.js")
    workspace = read(APP / "public/js/vetedge_clinical_workspace.bundle.js")
    editor = read(APP / "services/clinical_record_editor.py")
    lab = read(APP / "services/lab.py")

    for contract in (
        'type: "select"',
        "Selected Lab Tests",
        "Select one test at a time",
        "selected.map((row) => row.value)",
        "Remove",
    ):
        assert contract in picker
    assert "Select tests one at a time from the dropdown" in workspace
    assert "Selected Lab Tests" in workspace
    assert "lab_test_picker" in workspace
    assert '"fieldname": "lab_tests"' in editor
    assert "create_standalone_lab_order" in editor
    assert "normalize_lab_tests_payload" in lab


def test_lab_workflow_permissions_result_formats_and_completion_gate_remain_server_authoritative():
    lab = read(APP / "services/lab.py")
    for status in (
        "Draft",
        "Ordered",
        "Sample Collected",
        "Sent to Lab",
        "In Progress",
        "Result Pending",
        "Result Entered",
        "Awaiting Review",
        "Reviewed",
        "Completed",
        "Cancelled",
    ):
        assert f'"{status}"' in lab
    for result_format in ("Value Driven", "Text / Narrative", "Document Upload", "Mixed"):
        assert result_format in lab
    for contract in (
        "VALID_LAB_ORDER_STATUS_TRANSITIONS",
        "can_request_lab_tests",
        "can_enter_lab_results",
        "can_upload_lab_results",
        "can_review_lab_results",
        "validate_lab_order_completion_gate",
        "get_payment_gate_status",
    ):
        assert contract in lab


def test_edgesuite_clinical_workflow_actions_are_server_preflighted_and_not_status_edits():
    workflow = read(APP / "services/clinical_workflow_ui.py")
    editor = read(APP / "public/js/vetedge_clinical_record_editor.bundle.js")

    for contract in (
        "get_clinical_workflow_actions",
        "VALID_LAB_ORDER_STATUS_TRANSITIONS",
        "can_request_lab_tests",
        "can_enter_lab_results",
        "can_review_lab_results",
        "can_administer_vaccine",
        "Administer Vaccination",
        "Complete Lab Order",
    ):
        assert contract in workflow
    assert "clinical_workflow_ui.get_clinical_workflow_actions" in editor
    assert "runWorkflowAction" in editor
    assert "Workflow action blocked" in editor
    assert 'fieldname: "status"' not in editor


def test_draft_price_sync_and_submitted_invoice_locks_are_preserved():
    editor = read(APP / "services/clinical_record_editor.py")
    vaccination = read(APP / "services/vaccination.py")
    lab = read(APP / "services/lab.py")

    for contract in (
        "has_draft_invoice",
        "has_submitted_invoice",
        "safe_after_invoice",
        "create_or_update_modal_invoice",
        "save_lab_test_rate",
    ):
        assert contract in editor
    assert "Vaccination Rate cannot be changed after the linked invoice is submitted or cancelled." in vaccination
    assert "Lab order rates cannot be changed after the linked invoice is submitted." in lab


def test_payment_and_invoice_events_refresh_registration_and_service_billing_state():
    hooks = read(APP / "hooks.py")
    billing_modal = read(APP / "public/js/billing_modal.js")

    for contract in (
        "update_billing_sessions_from_invoice",
        "update_billing_sessions_from_payment_entry",
        "update_registration_status_from_invoice",
        "update_registration_status_from_payment_entry",
        "update_vaccination_status_from_invoice",
        "update_vaccination_status_from_payment_entry",
    ):
        assert contract in hooks
    assert "refreshSourceForm" in billing_modal
    assert "response.message?.state" in billing_modal
    assert "await refreshSourceForm()" in billing_modal


def test_edgesuite_mutations_are_platform_gated_without_replacing_domain_permissions():
    hooks = read(APP / "hooks.py")
    security = read(APP / "services/mutation_security.py")

    for endpoint in (
        "create_clinical_record",
        "save_clinical_record_editor",
        "delete_clinical_record",
        "save_lab_result_editor",
        "save_lab_test_rate",
        "transition_lab_order_status",
        "create_manual_registration_invoice",
    ):
        assert f"mutation_security.{endpoint}" in hooks
        assert f"def {endpoint}" in security
    assert "require_internal_user" in security
    assert "require_vetedge_platform_access" in security
    assert "can_access_patient" in security
    assert "can_access_branch_data" in security
