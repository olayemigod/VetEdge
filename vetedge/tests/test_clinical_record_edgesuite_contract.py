from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "vetedge"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_clinical_record_editor_supports_permission_safe_crud_and_billing_locks():
    service = read(APP / "services/clinical_record_editor.py")
    for doctype in (
        "Veterinary Lab Order",
        "Veterinary Vaccination Record",
        "Veterinary Vital Signs",
    ):
        assert doctype in service
    for contract in (
        "get_clinical_record_create_schema",
        "create_clinical_record",
        "save_clinical_record_editor",
        "delete_clinical_record",
        "has_draft_invoice",
        "has_submitted_invoice",
        "safe_after_invoice",
        "create_or_update_modal_invoice",
    ):
        assert contract in service
    assert "can_access_branch_data" in service
    assert "ignore_permissions=True" not in service
    assert "doc.save()" in service


def test_lab_create_and_result_modal_reuse_existing_result_and_payment_workflows():
    service = read(APP / "services/clinical_record_editor.py")
    bundle = read(APP / "public/js/vetedge_clinical_record_editor.bundle.js")
    lab = read(APP / "services/lab.py")
    for result_format in (
        "Value Driven",
        "Text / Narrative",
        "Document Upload",
        "Mixed",
    ):
        assert result_format in service
        assert result_format in lab
    for contract in (
        "create_standalone_lab_order",
        "get_active_lab_tests_for_picker",
        "can_enter_lab_results",
        "can_upload_lab_results",
        "get_lab_result_editor",
        "save_lab_result_editor",
        "save_lab_test_rate",
    ):
        assert contract in service
    for contract in (
        "Enter Result",
        "View / Edit Result",
        "Upload Result",
        "Open Upload",
        "Upload Report",
        "Open Uploaded Report",
        "Change Price",
        "/api/method/upload_file",
    ):
        assert contract in bundle


def test_clinical_record_editor_is_edgesuite_native_and_full_crud_visible():
    bundle = read(APP / "public/js/vetedge_clinical_record_editor.bundle.js")
    for contract in (
        "VetEdgeEdgeModalPresenter",
        "Save Changes",
        "Billing & Payment",
        "Delete Permanently",
        "Create Clinical Record",
        "VetEdgeClinicalRecordEditor",
    ):
        assert contract in bundle
    assert "frappe.ui.Dialog" not in bundle


def test_resource_center_exposes_create_edit_and_readable_patients_for_lab_and_vaccination():
    bridge = read(APP / "public/js/vetedge_resource_center_clinical_bridge.js")
    loader = read(APP / "veterinary/page/vetedge_resource_center/vetedge_resource_center.js")
    assert '"lab-orders": "Veterinary Lab Order"' in bridge
    assert 'vaccinations: "Veterinary Vaccination Record"' in bridge
    for contract in (
        "New Lab Order",
        "New Vaccination",
        "View / Edit",
        "VetEdgeClinicalRecordEditor",
        "get_patient_labels",
        "data-patient-id",
    ):
        assert contract in bridge
    for asset in (
        "vetedge_edge_modal_presenter.bundle.js",
        "vetedge_billing_edgesuite.bundle.js",
        "vetedge_clinical_record_editor.bundle.js",
        "vetedge_resource_center_clinical_bridge.js",
    ):
        assert asset in loader


def test_vital_signs_has_first_class_edgesuite_crud_center_and_readable_patients():
    page_dir = APP / "veterinary/page/vetedge_vitals_center"
    component = APP / "public/js/vetedge_vitals_center/VetEdgeVitalsCenter.vue"
    bundle = APP / "public/js/vetedge_vitals_center.bundle.js"
    assert (page_dir / "vetedge_vitals_center.json").exists()
    assert (page_dir / "vetedge_vitals_center.js").exists()
    assert component.exists()
    assert bundle.exists()
    content = read(component)
    for contract in (
        "EdgeAppShell",
        "EdgeFilterBar",
        "EdgeLinkField",
        "EdgeDataTable",
        "VetEdgeClinicalRecordEditor",
        'active-route="/desk/vetedge-vitals-center"',
        "New Vital Signs",
        "patient_name",
        "get_patient_labels",
    ):
        assert contract in content
    vital_list = read(APP / "veterinary/doctype/veterinary_vital_signs/veterinary_vital_signs_list.js")
    vital_form = read(APP / "veterinary/doctype/veterinary_vital_signs/veterinary_vital_signs.js")
    assert "/desk/vetedge-vitals-center" in vital_list
    assert "/desk/vetedge-vitals-center?name=" in vital_form


def test_structured_reports_publish_readable_patient_names_without_losing_ids():
    display_names = read(APP / "services/display_names.py")
    reporting = read(APP / "services/reporting_logic_v3.py")
    assert "get_patient_display_map" in display_names
    assert '"patient_name"' in display_names
    assert 'row["patient_id"] = patient_id' in reporting
    assert 'row["patient_name"] = display_map.get(patient_id, patient_id)' in reporting
    assert 'readable["fieldname"] = "patient_name"' in reporting


def test_billing_modal_uses_shared_consultation_surface_and_inline_payment_actions():
    alignment = read(APP / "public/js/vetedge_billing_modal_alignment.js")
    billing = read(APP / "public/js/billing_modal.js")
    hooks = read(APP / "hooks.py")
    for contract in (
        "Payment Summary",
        "ve-billing-payment-actions",
        "--edge-color-brand-600",
        "--edge-color-surface",
        "--edge-color-ink-950",
    ):
        assert contract in alignment
    for contract in (
        "can_create_or_update_invoice",
        "can_submit_invoice",
        "can_record_payment",
        "renderLinkedInvoiceAction",
        "Payment Summary",
    ):
        assert contract in billing
    assert "vetedge_billing_modal_alignment.js" in hooks


def test_planned_treatment_is_an_edgesuite_report_not_a_clinical_service_surface():
    page_dir = APP / "veterinary/page/vetedge_treatment_plan_report"
    component = APP / "public/js/vetedge_treatment_plan_report/VetEdgeTreatmentPlanReport.vue"
    bundle = APP / "public/js/vetedge_treatment_plan_report.bundle.js"
    provider = APP / "services/treatment_plan_report.py"
    query_report = APP / "veterinary/report/planned_treatment/planned_treatment.js"
    alignment = APP / "public/js/vetedge_sidebar_qa_alignment.js"
    for path in (
        page_dir / "vetedge_treatment_plan_report.json",
        page_dir / "vetedge_treatment_plan_report.js",
        component,
        bundle,
        provider,
    ):
        assert path.exists(), path
    component_content = read(component)
    provider_content = read(provider)
    assert 'active-route="/desk/vetedge-treatment-plan-report"' in component_content
    assert "EdgeFilterBar" in component_content
    assert "EdgeDataTable" in component_content
    assert 'execute_structured_report("Planned Treatment"' in provider_content
    assert "/desk/vetedge-treatment-plan-report" in read(query_report)
    sidebar_alignment = read(alignment)
    assert "movePlannedTreatmentToReports" in sidebar_alignment
    assert 'section(shell, "Reports")' in sidebar_alignment
    assert "Planned Treatment" in sidebar_alignment


def test_sidebar_alignment_focuses_vitals_under_clinical_not_dashboard():
    alignment = read(APP / "public/js/vetedge_sidebar_qa_alignment.js")
    hooks = read(APP / "hooks.py")
    assert 'path === "/desk/vetedge-vitals-center"' in alignment
    assert 'section(shell, "Clinical")' in alignment
    assert 'itemIn(clinical, "Vital Signs")' in alignment
    assert "expandOnly" in alignment
    assert "vetedge_sidebar_qa_alignment.js" in hooks


def test_medical_history_readability_and_first_chart_render_are_protected():
    patch = read(APP / "public/js/vetedge_medical_history_qa_patch.js")
    css = read(APP / "public/css/vetedge_medical_history_qa.css")
    loader = read(APP / "veterinary/page/veterinary_medical_history/veterinary_medical_history.js")
    for contract in (
        "requestAnimationFrame",
        "Veterinary Lab Order",
        "Veterinary Vaccination Record",
        "Veterinary Vital Signs",
        "VetEdgeClinicalRecordEditor",
    ):
        assert contract in patch
    assert "--edge-color-ink-950" in css
    assert 'data-edge-appearance="dark"' in css
    for asset in (
        "vetedge_clinical_record_editor.bundle.js",
        "vetedge_medical_history_qa.css",
        "vetedge_medical_history_qa_patch.js",
    ):
        assert asset in loader
