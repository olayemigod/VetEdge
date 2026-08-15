from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_one_canonical_billing_modal_is_shared_across_services():
    hooks = read(APP / "hooks.py")
    legacy = read(APP / "public/js/billing_modal.js")
    shared = read(APP / "public/js/vetedge_shared_billing_edgesuite.js")
    compatibility = read(APP / "public/js/vetedge_billing_edgesuite.bundle.js")

    assert '"/assets/vetedge/js/billing_modal.js"' in hooks
    assert "vetedge_shared_billing_edgesuite.js" in hooks
    assert "window.vetedgeBillingModal" in legacy
    assert "VetEdgeEdgeModalPresenter" in shared
    assert "new frappe.ui.Dialog" not in shared
    assert 'type: "select"' in shared
    assert 'type: "link"' in shared
    assert "must never replace window.vetedgeBillingModal" in compatibility
    assert "window.vetedgeBillingModal =" not in compatibility


def test_shared_billing_server_supports_all_billable_sources_and_security_layers():
    service = read(APP / "services/billing_modal.py")
    security = read(APP / "services/billing_state_security.py")
    alignment = read(APP / "services/billing_context_alignment.py")
    hooks = read(APP / "hooks.py")

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
    for endpoint in (
        "get_billing_modal_state",
        "create_or_update_modal_invoice",
        "submit_modal_invoice",
        "record_modal_invoice_payment",
    ):
        assert f'billing_modal.{endpoint}": "vetedge.services.billing_context_alignment.{endpoint}' in hooks
        assert f"def {endpoint}" in alignment
        assert f"def {endpoint}" in security
    assert 'frappe.has_permission("Sales Invoice", "submit", doc=invoice)' in security
    assert 'frappe.has_permission("Payment Entry", "create")' in security
    assert 'frappe.has_permission("Payment Entry", "submit")' in security
    assert "_normalize_result_state" in security


def test_owner_outstanding_context_is_explicit_and_patient_aware():
    alignment = read(APP / "services/billing_context_alignment.py")
    shared = read(APP / "public/js/vetedge_shared_billing_edgesuite.js")

    assert 'state["outstanding_context_scope"] = "owner"' in alignment
    assert 'row["patient_name"]' in alignment
    assert "Veterinary Billing Session" in alignment
    assert "Other Outstanding Invoices for this Owner" in shared
    assert 'fieldname: "patient_name"' in shared
    assert "same Pet Owner/Customer" in shared


def test_registration_has_standalone_shared_billing_and_payment_path():
    registration = read(APP / "services/registration_billing.py")
    alignment = read(APP / "services/registration_state_alignment.py")
    patient_form = read(APP / "veterinary/doctype/veterinary_patient/veterinary_patient.js")
    resource_api = read(APP / "services/resource_center_v2.py")
    resource_component = read(APP / "public/js/vetedge_resource_center/VetEdgeResourceCenter.vue")
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
    assert "vetedgeBillingModal.open" in patient_form
    for label in (
        "Bill Registration",
        "Submit Registration Invoice",
        "Pay Registration",
        "Pay Registration Balance",
        "View Registration Payment",
        "Rebill Registration",
    ):
        assert label in resource_api
    assert "row._registration_action.label" in resource_component
    assert "align_patient_registration_state" in alignment
    assert "update_registration_status_from_invoice_aligned" in hooks
    assert "update_registration_status_from_payment_entry_aligned" in hooks


def test_resource_center_v3_preserves_patient_filters_and_adds_clinical_filters():
    hooks = read(APP / "hooks.py")
    v2 = read(APP / "services/resource_center_v2.py")
    v3 = read(APP / "services/resource_center_v3.py")
    hardening = read(APP / "public/js/vetedge_resource_center_hardening.js")

    assert "resource_center_v3.get_resource_page" in hooks
    assert "v2._resource_page" in v3
    for fieldname in ("default_branch", "status", "registration_status", "species"):
        assert fieldname in v2
    for fieldname in (
        "patient",
        "service_branch",
        "status",
        "from_date",
        "to_date",
        "vaccine",
        "lab_test",
    ):
        assert fieldname in v3
    assert '"unsupported_required_fields": []' in v3
    assert '"summary_label": "Branch Scope"' in v3
    assert "Apply Clinical Filters" in hardening
    assert 'querySelector(".vetedge-resource-notice")?.remove?.()' in hardening


def test_patient_inline_masters_species_breed_cascade_and_deceased_flag_are_safe():
    state = read(APP / "services/resource_editor_state.py")
    quick = read(APP / "public/js/vetedge_resource_center/VetEdgeResourceQuickEditor.vue")
    inline = read(APP / "services/inline_master.py")
    patient = read(APP / "services/patient.py")

    assert "resource_editor_state.get_resource_editor" in read(APP / "hooks.py")
    assert 'if not name and fieldname == "is_deceased"' in state
    assert 'payload["is_deceased"] = 0' in state
    assert 'value === "1"' in quick
    assert ':can-create="Boolean(field.can_create)"' in quick
    assert "VetEdgeInlineMasterCreator" in quick
    assert 'field.fieldname === "species"' in quick
    assert 'this.values.breed = ""' in quick
    for doctype in ("Customer", "Veterinary Species", "Veterinary Breed"):
        assert doctype in inline
    assert "get_doc_before_save" in patient
    assert 'doc.status = "Active"' in patient


def test_deceased_patient_service_guard_is_server_side():
    hooks = read(APP / "hooks.py")
    guard = read(APP / "services/patient_service_guard.py")

    assert "assert_patient_accepts_new_service" in guard
    assert "patient_is_deceased" in guard
    assert "BLOCKED_DELIVERY_TRANSITIONS" in guard
    for doctype in (
        "Veterinary Appointment",
        "Veterinary Consultation",
        "Veterinary Vital Signs",
        "Veterinary Lab Order",
        "Veterinary Vaccination Record",
        "Veterinary Hospitalisation",
        "Pet Grooming Appointment",
        "Pet Grooming Session",
        "Pet Boarding Booking",
        "Pet Boarding Stay",
    ):
        assert f'"{doctype}"' in hooks
    assert "patient_service_guard.enforce_patient_service_guard" in hooks


def test_lab_multi_test_picker_extension_preserves_workflow_and_draft_invoice_sync():
    picker = read(APP / "public/js/vetedge_lab_order_picker_patch.js")
    add_ui = read(APP / "public/js/vetedge_lab_order_add_tests.js")
    extension = read(APP / "services/lab_order_extensions.py")
    lab = read(APP / "services/lab.py")

    assert 'type: "select"' in picker
    assert "Selected Lab Tests" in picker
    assert "selected.map((row) => row.value)" in picker
    assert "Add Lab Tests" in add_ui
    assert "Add Selected Tests" in add_ui
    assert "get_addable_lab_tests" in extension
    assert "add_lab_tests" in extension
    assert "has_submitted_invoice" in extension
    assert "has_draft_invoice" in extension
    assert "create_or_update_modal_invoice" in extension
    for result_format in ("Value Driven", "Text / Narrative", "Document Upload", "Mixed"):
        assert result_format in lab


def test_vaccination_fields_follow_workflow_payment_and_reference_display():
    state = read(APP / "services/clinical_record_state_v2.py")
    alignment = read(APP / "services/vaccination_state_alignment.py")
    display = read(APP / "services/display_labels.py")
    hooks = read(APP / "hooks.py")

    for fieldname in (
        "administered_by",
        "administered_on",
        "next_vaccination_appointment",
        "batch_no",
        "billing_item",
        "amount",
        "linked_invoice",
        "stock_entry_reference",
    ):
        assert fieldname in state
    assert "has_submitted_invoice" in state
    assert 'field["value"] = ""' in state
    assert "align_vaccination_administration_metadata" in hooks
    assert "PRE_ADMIN_STATUSES" in alignment
    assert '"Sales Invoice"' in display
    assert '"Veterinary Patient": "patient_name"' in display
    assert "get_display_label" in state


def test_payment_and_invoice_events_refresh_registration_and_service_billing_state():
    hooks = read(APP / "hooks.py")
    for contract in (
        "update_billing_sessions_from_invoice",
        "update_billing_sessions_from_payment_entry",
        "update_registration_status_from_invoice_aligned",
        "update_registration_status_from_payment_entry_aligned",
        "update_vaccination_status_from_invoice",
        "update_vaccination_status_from_payment_entry",
    ):
        assert contract in hooks


def test_edgesuite_mutations_remain_permission_and_platform_gated():
    hooks = read(APP / "hooks.py")
    security = read(APP / "services/mutation_security.py")
    inline = read(APP / "services/inline_master.py")
    extension = read(APP / "services/lab_order_extensions.py")

    assert "require_internal_user" in security
    assert "require_vetedge_platform_access" in security
    assert "frappe.has_permission" in inline
    assert "require_vetedge_platform_access" in extension
    assert "can_request_lab_tests" in extension
    for endpoint in (
        "create_clinical_record",
        "save_clinical_record_editor",
        "delete_clinical_record",
        "save_lab_result_editor",
        "save_lab_test_rate",
        "transition_lab_order_status",
    ):
        assert f"mutation_security.{endpoint}" in hooks


# Run the focused hardening contract whenever this established fast-gate file is
# selected by CI, without duplicating its assertions here.
from vetedge.tests.test_clinical_workflow_hardening_contract import *  # noqa: E402,F403
