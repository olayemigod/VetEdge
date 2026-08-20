from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_medical_history_excludes_non_clinical_lab_and_vaccination_states():
    source = read("vetedge/services/medical_history_integrity.py")
    assert 'LAB_HISTORY_STATUSES = {' in source
    assert '"Draft"' not in source.split("LAB_HISTORY_STATUSES = {", 1)[1].split("}", 1)[0]
    assert '"Cancelled"' not in source.split("LAB_HISTORY_STATUSES = {", 1)[1].split("}", 1)[0]
    assert 'VACCINATION_HISTORY_STATUSES = {"Administered"}' in source
    assert "def _dedupe" in source
    assert 'result["labs"] = filter_medical_history_rows' in source
    assert 'result["vaccinations"] = filter_medical_history_rows' in source


def test_medical_history_routes_through_integrity_wrappers():
    hooks = read("vetedge/hooks.py")
    assert 'vetedge.services.medical_history.get_patient_medical_history_view' in hooks
    assert 'vetedge.services.medical_history_integrity.get_patient_medical_history_view' in hooks
    assert 'vetedge.services.medical_history.get_patient_medical_history' in hooks
    assert 'vetedge.services.medical_history_integrity.get_patient_medical_history' in hooks
    assert 'vetedge.services.medical_history_lazy.get_patient_medical_history_section' in hooks
    assert 'vetedge.services.medical_history_integrity.get_patient_medical_history_section' in hooks


def test_lab_and_vaccination_consultation_links_are_patient_scoped_and_open_only():
    source = read("vetedge/services/clinical_consultation_context.py")
    assert 'CLOSED_CONSULTATION_STATUSES = {"Completed", "Cancelled"}' in source
    assert '"patient": patient' in source
    assert '"status": ["not in", sorted(CLOSED_CONSULTATION_STATUSES)]' in source
    assert 'The selected Consultation must belong to patient' in source
    assert 'Only an open Consultation for this patient can be linked.' in source
    assert '"Veterinary Lab Order": "consultation"' in source
    assert '"Veterinary Vaccination Record": "linked_consultation"' in source


def test_standalone_vitals_consultation_picker_is_patient_scoped_optional_and_readable():
    context = read("vetedge/services/clinical_consultation_context.py")
    vitals = read("vetedge/services/vitals.py")
    presenter = read("vetedge/public/js/vetedge_edge_modal_presenter.bundle.js")

    assert "CREATE_CONTEXT_FIELDS" in context
    assert '"Veterinary Vital Signs": "consultation"' in context
    assert "fieldname = CREATE_CONTEXT_FIELDS.get(doctype)" in context
    assert 'field["link_search_context_field"] = "patient"' in context
    assert 'field["description"] = _("Optional. Shows only open consultations for the selected patient.")' in context
    assert '["patient", "service_branch", "status"]' in vitals
    assert "_consultation_link_is_new_or_changed" in vitals
    assert "CLOSED_CONSULTATION_STATUSES" in vitals
    assert 'field.type === "link" && !value' in presenter
    assert "setLinkFieldLabel" in presenter
    assert "onSelect: (option) => this.setLinkFieldLabel(field, option)" in presenter


def test_consultation_link_becomes_read_only_after_assignment_or_progress():
    source = read("vetedge/services/clinical_consultation_context.py")
    assert 'LAB_CONTEXT_EDITABLE_STATUSES = {"Draft", "Ordered"}' in source
    assert 'VACCINATION_CONTEXT_EDITABLE_STATUSES = {"Draft"}' in source
    assert 'if not fieldname or _clean(doc.get(fieldname)):' in source
    assert 'Consultation is read-only after it has been linked to this clinical record.' in source
    assert 'Consultation can only be linked before billing or clinical processing has started.' in source


def test_edgesuite_consultation_search_cascades_from_patient():
    source = read("vetedge/public/js/vetedge_clinical_record_editor.bundle.js")
    assert "field?.link_search_method" in source
    assert "field.link_search_context_field" in source
    assert "buildFieldSpecs" in source
    assert "dependent.linkSearchContextField !== field.fieldname" in source
    assert 'presenterView?.setField?.(dependent, "")' in source


def test_native_lab_and_vaccination_context_patch_uses_same_rules():
    source = read("vetedge/public/js/vetedge_clinical_consultation_context.js")
    assert 'const CLOSED = ["Completed", "Cancelled"]' in source
    assert 'patient: frm.doc.patient' in source
    assert 'status: ["not in", CLOSED]' in source
    assert 'frappe.ui.form.on("Veterinary Lab Order"' in source
    assert 'frappe.ui.form.on("Veterinary Vaccination Record"' in source