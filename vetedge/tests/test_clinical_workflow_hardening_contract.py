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
    assert 'if not name and fieldname == "is_deceased"' in state
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


def test_vaccination_state_is_workflow_billing_and_stock_aware():
    state = read("vetedge/services/clinical_record_state_v2.py")
    alignment = read("vetedge/services/vaccination_state_alignment.py")
    vaccination = read("vetedge/services/vaccination.py")
    expiry = read("vetedge/services/expiry_control.py")
    hooks = read("vetedge/hooks.py")
    clinical_bundle = read("vetedge/public/js/vetedge_clinical_workspace.bundle.js")

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
    assert 'state["batch_selection_policy"] = "FEFO"' in state
    assert "Selected automatically from available non-expired vaccine stock" in state
    assert "allocate_item_batches" in vaccination
    assert "manual_batch_no=doc.batch_no" in vaccination
    assert "get_available_valid_batches" in expiry
    assert "allocate_fefo_batches" in expiry
    assert "align_vaccination_administration_metadata" in hooks
    assert "PRE_ADMIN_STATUSES" in alignment
    assert "Administration user/time, batch, stock entry and linked invoice" in clinical_bundle
    vaccination_creation = clinical_bundle.split("function vaccinationFields", 1)[1].split(
        "function openHospitalisationModal", 1
    )[0]
    assert "fieldname: 'administered_on'" not in vaccination_creation
    assert "serverDatetime(values.administered_on)" not in vaccination_creation


def test_vaccination_joins_an_existing_billing_cycle_without_creating_or_double_syncing_one():
    controller = read(
        "vetedge/veterinary/doctype/veterinary_vaccination_record/veterinary_vaccination_record.py"
    )
    plan = read("vetedge/services/consultation_billing_plan.py")

    assert "def _sync_existing_vaccination_billing_session" in controller
    assert 'if doc.get("linked_consultation"):' in controller
    assert 'frappe.get_doc("Veterinary Consultation", doc.linked_consultation)' in controller
    assert "_sync_active_consultation_billing_session(consultation)" in controller
    assert 'getattr(flags, "vetedge_billing_core_syncing", False)' in controller
    assert "resolve_billing_session" in controller
    assert "if not session:" in controller
    assert "get_or_create_billing_session" not in controller
    assert "_session_has_vaccination_charge" in controller
    assert "sync_single_source_to_billing_session" in controller
    assert "sync_session_charges_to_invoice" in controller
    assert controller.count("_sync_existing_vaccination_billing_session(self)") == 2
    assert "sync_vaccination_to_consultation_plan" in controller

    # Billing Core itself invokes these projection functions while restoring
    # source-linked Consultation rows. They must never recursively save the same
    # Billing Session that the outer sync already holds.
    lab_projection = plan.split("def sync_lab_order_to_consultation_plan", 1)[1].split(
        "def sync_vaccination_to_consultation_plan", 1
    )[0]
    vaccination_projection = plan.split("def sync_vaccination_to_consultation_plan", 1)[1].split(
        "def _has_source_row", 1
    )[0]
    assert "_sync_active_consultation_billing_session" not in lab_projection
    assert "_sync_active_consultation_billing_session" not in vaccination_projection
    assert "def _sync_active_consultation_billing_session" in plan


def test_lab_order_supports_multi_test_extension_and_draft_billing_sync():
    service = read("vetedge/services/lab_order_extensions.py")
    frontend = read("vetedge/public/js/vetedge_lab_order_add_tests.js")
    loader = read("vetedge/veterinary/page/vetedge_resource_center/vetedge_resource_center.js")
    controller = read(
        "vetedge/veterinary/doctype/veterinary_lab_order/veterinary_lab_order.py"
    )

    assert "get_addable_lab_tests" in service
    assert "add_lab_tests" in service
    assert "has_submitted_invoice" in service
    assert "has_draft_invoice" in service
    assert "create_or_update_modal_invoice" in service
    assert "Add Lab Tests" in frontend
    assert "Add Selected Tests" in frontend
    assert 'type: "select"' in frontend
    assert "VetEdgeLabOrderAddTests?.install?.()" in loader

    # Lab plan projection is followed by one explicit active Consultation
    # Billing Session reconciliation from the Lab controller, never recursively
    # from the projection function itself.
    assert "def _sync_linked_consultation_billing_session" in controller
    assert "_sync_active_consultation_billing_session(consultation)" in controller
    assert 'getattr(flags, "vetedge_billing_core_syncing", False)' in controller
    assert controller.count("_sync_linked_consultation_billing_session(self)") == 2


def test_lab_multi_test_results_advance_parent_only_after_all_active_rows_have_results():
    service = read("vetedge/services/lab.py")
    workflow = service.split("def normalize_lab_order_result_workflow", 1)[1].split(
        "def validate_lab_order_status_requirements", 1
    )[0]

    assert "all_results_entered = all(_row_has_lab_result_content(row) for row in active_rows)" in workflow
    assert "if not all_results_entered:" in workflow
    assert workflow.index("if not all_results_entered:") < workflow.index('doc.status = "Awaiting Review"')
    assert workflow.index("if not all_results_entered:") < workflow.index('doc.status = "Result Entered"')


def test_lab_cancel_uses_accounting_safe_reconciliation_and_cleans_all_notification_links():
    cancellation = read("vetedge/services/lab_cancellation.py")
    editor = read("vetedge/services/clinical_record_editor.py")
    state_v2 = read("vetedge/services/clinical_record_state_v2.py")
    controller = read(
        "vetedge/veterinary/doctype/veterinary_lab_order/veterinary_lab_order.py"
    )

    assert 'HARD_BLOCK_PAYMENT_STATES = {"Partly Paid", "Paid"}' in cancellation
    assert 'ALLOWED_BILLING_CONFIRMATIONS = {"remove_empty_draft_invoice", "cancel_unpaid_invoice"}' in cancellation
    assert "sync_session_charges_to_invoice" in cancellation
    assert "submitted invoice" in cancellation.lower()
    assert "active or unproven charges for other services" in cancellation
    assert 'filters={"invoice": invoice_name}' in cancellation
    assert "extract_charge_key_from_invoice_item" in cancellation
    assert "target_charge_keys" in cancellation
    assert "Veterinary Notification Item" in cancellation
    assert '"status": "Archived"' in cancellation
    assert '"reference_doctype": None' in cancellation
    assert "_detach_deleted_lab_billing_links" in cancellation

    # The normal Veterinary UI exposes Cancel, not destructive Lab deletion.
    assert "def _align_lab_state" in state_v2
    assert 'state["can_delete"] = False' in state_v2
    assert "Cancel is the supported Lab Order correction path" in state_v2

    # The custom delivery audit log is retained but its Dynamic Link is cleared
    # in the same transaction when a Lab cancellation/delete is attempted.
    assert 'VETERINARY_NOTIFICATION_LOG_DOCTYPE = "Veterinary Notification Log"' in controller
    assert "def _detach_veterinary_notification_logs" in controller
    assert 'filters={"reference_doctype": "Veterinary Lab Order", "reference_name": lab_order}' in controller
    assert '{"reference_doctype": None, "reference_name": None}' in controller
    cancellation_validate = controller.split("def validate(self)", 1)[1].split("def after_insert", 1)[0]
    assert 'if self.status == "Cancelled":' in cancellation_validate
    assert "_detach_veterinary_notification_logs(self.name)" in cancellation_validate

    # Server-side delete safety remains as a defensive/admin backstop even though
    # the normal EdgeSuite workflow does not present a Delete action.
    assert "build_lab_order_cancellation_preflight" in editor


def test_resource_center_native_source_owns_summary_filters_labels_and_patient_shortcut():
    service = read("vetedge/services/resource_center_v3.py")
    component = read("vetedge/public/js/vetedge_resource_center/VetEdgeResourceCenter.vue")
    hardening = read("vetedge/public/js/vetedge_resource_center_hardening.js")
    bridge = read("vetedge/public/js/vetedge_resource_center_clinical_bridge.js")
    clinical_bundle = read("vetedge/public/js/vetedge_clinical_workspace.bundle.js")

    assert '"unsupported_required_fields": []' in service
    assert '"summary_label": "Branch Scope"' in service
    assert '"lab-orders"' in service
    assert '"vaccinations"' in service
    for field in ("patient", "service_branch", "status", "from_date", "to_date", "vaccine", "lab_test"):
        assert field in service
        assert field in component

    assert "Medical History" in component
    assert "openMedicalHistory(row)" in component
    assert "/desk/veterinary-medical-history?patient=${encodeURIComponent(row.name)}" in component
    assert "New Consultation" not in component
    assert "openNewConsultation(row)" not in component
    assert "page.summary_label || 'Branch Scope'" in component
    assert "row?._display?.[column.fieldname]" in component
    assert "clinicalStatusOptions" in component
    assert "New Lab Order" in component
    assert "New Vaccination" in component
    assert "View / Edit" in component
    assert "Full ERPNext form required for create or edit" not in component
    assert "Use the full ERPNext form for this record" not in component
    assert "accessLabel" not in component
    assert ">Access<" not in component

    assert "frappe.call = wrapped" not in hardening
    assert "MutationObserver" not in hardening
    assert "MutationObserver" not in bridge
    assert "Compatibility shim only" in hardening
    assert "Compatibility shim only" in bridge

    assert "params.get('patient')" in clinical_bundle
    assert "this.selectPatient?.(patient)" in clinical_bundle
    assert "/desk/vetedge-clinical-workspace?new=1" in clinical_bundle


def test_reference_documents_keep_reference_numbers_and_masters_use_titles():
    display = read("vetedge/services/display_labels.py")
    state = read("vetedge/services/clinical_record_state_v2.py")

    assert '"Sales Invoice"' in display
    assert '"Veterinary Patient": "patient_name"' in display
    assert '"Customer": "customer_name"' in display
    assert '"Veterinary Species": "species_name"' in display
    assert '"Veterinary Breed": "breed_name"' in display
    assert "get_display_label" in state
