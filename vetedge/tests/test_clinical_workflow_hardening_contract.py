from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_shared_billing_uses_edgesuite_and_owner_patient_context():
    billing = read("vetedge/public/js/vetedge_shared_billing_edgesuite.js")
    backend = read("vetedge/services/billing_context_alignment.py")
    hooks = read("vetedge/hooks.py")

    assert "VetEdgeEdgeModalPresenter" in billing
    assert "new frappe.ui.Dialog" not in billing
    assert 'type: "select"' in billing
    assert 'type: "link"' in billing
    assert "Other Outstanding Invoices for this Owner" in billing
    assert 'fieldname: "patient_name"' in billing
    assert "outstanding_context_scope" in backend
    assert 'row["patient_name"]' in backend
    assert "billing_context_alignment.get_billing_modal_state" in hooks


def test_patient_quick_editor_normalizes_check_values_and_supports_inline_masters():
    editor = read("vetedge/public/js/vetedge_resource_center/VetEdgeResourceQuickEditor.vue")
    state = read("vetedge/services/resource_editor_state.py")
    inline = read("vetedge/services/inline_master.py")

    assert 'value === "1"' in editor
    assert ':can-create="Boolean(field.can_create)"' in editor
    assert ':creator="field.can_create ? (term) => createLinkedMaster(field, term) : null"' in editor
    assert 'field.fieldname === "species"' in editor
    assert 'this.values.breed = ""' in editor
    assert 'if (!name and fieldname == "is_deceased")' in state
    assert 'payload["is_deceased"] = 0' in state
    for doctype in ("Customer", "Veterinary Species", "Veterinary Breed"):
        assert doctype in inline


def test_deceased_patient_guard_is_server_side_for_service_doctypes():
    hooks = read("vetedge/hooks.py")
    guard = read("vetedge/services/patient_service_guard.py")
    patient = read("vetedge/services/patient.py")

    for doctype in (
        "Veterinary Appointment",
        "Veterinary Consultation",
        "Veterinary Vital Signs",
        "Veterinary Lab Order",
        "Veterinary Vaccination Record",
        "Pet Grooming Appointment",
        "Pet Grooming Session",
        "Pet Boarding Booking",
    ):
        assert f'"{doctype}"' in hooks
    assert "enforce_patient_service_guard" in hooks
    assert "assert_patient_accepts_new_service" in guard
    assert "doc.is_deceased = 0" in patient
    assert 'doc.status = "Active"' in patient


def test_vaccination_state_is_workflow_and_billing_aware():
    state = read("vetedge/services/clinical_record_state_v2.py")
    alignment = read("vetedge/services/vaccination_state_alignment.py")
    hooks = read("vetedge/hooks.py")

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


def test_lab_order_supports_multi_test_extension_and_draft_billing_sync():
    service = read("vetedge/services/lab_order_extensions.py")
    frontend = read("vetedge/public/js/vetedge_lab_order_add_tests.js")

    assert "get_addable_lab_tests" in service
    assert "add_lab_tests" in service
    assert "has_submitted_invoice" in service
    assert "has_draft_invoice" in service
    assert "create_or_update_modal_invoice" in service
    assert "Add Lab Tests" in frontend
    assert "Add Selected Tests" in frontend
    assert 'type: "select"' in frontend


def test_resource_center_removes_generic_readonly_banner_and_adds_filters():
    service = read("vetedge/services/resource_center_v3.py")
    frontend = read("vetedge/public/js/vetedge_resource_center_hardening.js")

    assert '"unsupported_required_fields": []' in service
    assert '"summary_label": "Branch Scope"' in service
    assert '"lab-orders"' in service
    assert '"vaccinations"' in service
    for field in ("patient", "service_branch", "status", "from_date", "to_date", "vaccine", "lab_test"):
        assert field in service
    assert 'querySelector(".vetedge-resource-notice")?.remove?.()' in frontend
    assert 'button.textContent = __("New Consultation")' in frontend
    assert "Apply Clinical Filters" in frontend


def test_reference_documents_keep_reference_numbers_and_masters_use_titles():
    display = read("vetedge/services/display_labels.py")
    state = read("vetedge/services/clinical_record_state_v2.py")

    assert '"Sales Invoice"' in display
    assert '"Veterinary Patient": "patient_name"' in display
    assert '"Customer": "customer_name"' in display
    assert '"Veterinary Species": "species_name"' in display
    assert '"Veterinary Breed": "breed_name"' in display
    assert "get_display_label" in state
