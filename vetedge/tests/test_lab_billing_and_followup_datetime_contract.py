import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return ROOT.joinpath(relative_path).read_text(encoding="utf-8")


def field_from_doctype(relative_path: str, fieldname: str) -> dict:
    payload = json.loads(read(relative_path))
    return next(field for field in payload["fields"] if field.get("fieldname") == fieldname)


def test_consultation_lab_order_resyncs_an_existing_billing_cycle():
    content = read("vetedge/services/consultation_billing_plan.py")
    lab_block = content.split("def sync_lab_order_to_consultation_plan", 1)[1].split(
        "def sync_vaccination_to_consultation_plan", 1
    )[0]
    helper = content.split("def _sync_active_consultation_billing_session", 1)[1]

    assert "_save_consultation(consultation)" in lab_block
    assert "_sync_active_consultation_billing_session(consultation)" in lab_block
    assert lab_block.index("_save_consultation(consultation)") < lab_block.index(
        "_sync_active_consultation_billing_session(consultation)"
    )
    assert "is_billing_sessions_enabled" in helper
    assert "resolve_billing_session(CONSULTATION_DOCTYPE, consultation.name)" in helper
    assert "if not session:" in helper
    assert "sync_source_to_billing_session(CONSULTATION_DOCTYPE, consultation.name)" in helper
    assert "frappe.db.set_value(\"Sales Invoice\"" not in helper


def test_consultation_follow_up_field_is_datetime_and_edgesuite_preserves_time():
    field = field_from_doctype(
        "vetedge/veterinary/doctype/veterinary_consultation/veterinary_consultation.json",
        "follow_up_date",
    )
    component = read("vetedge/public/js/vetedge_clinical_workspace/VetEdgeClinicalWorkspace.vue")
    controller = read("vetedge/veterinary/doctype/veterinary_consultation/veterinary_consultation.py")

    assert field["fieldtype"] == "Datetime"
    assert "Date/Time" in field["label"]
    assert 'type="datetime-local" label="Follow-up Date/Time"' in component
    assert "follow_up_date: localDatetime(values.follow_up_date)" in component
    assert "follow_up_date: serverDatetime(this.form.follow_up_date)" in component
    assert "sync_follow_up_appointment_from_consultation(self)" in controller


def test_vaccination_next_due_is_datetime_across_standalone_and_consultation_ui():
    field = field_from_doctype(
        "vetedge/veterinary/doctype/veterinary_vaccination_record/veterinary_vaccination_record.json",
        "next_due_date",
    )
    clinical_bundle = read("vetedge/public/js/vetedge_clinical_workspace.bundle.js")
    record_editor = read("vetedge/public/js/vetedge_clinical_record_editor.bundle.js")

    assert field["fieldtype"] == "Datetime"
    assert "Date/Time" in field["label"]
    assert "next_due_date', label: tr('Next Due Date/Time'), type: 'datetime-local'" in clinical_bundle
    assert 'Datetime: "datetime-local"' in record_editor


def test_vaccination_appointment_generation_preserves_selected_or_calculated_time():
    vaccination = read("vetedge/services/vaccination.py")
    native_form = read(
        "vetedge/veterinary/doctype/veterinary_vaccination_record/veterinary_vaccination_record.js"
    )

    calculate_block = vaccination.split("def calculate_next_due_date", 1)[1].split(
        "def get_vaccine_defaults", 1
    )[0]
    appointment_block = vaccination.split("def create_next_due_vaccination_appointment", 1)[1].split(
        "def is_appointment_creation_enabled", 1
    )[0]

    assert "add_days(get_datetime(doc.administered_on), default_days)" in calculate_block
    assert "09:00:00" not in appointment_block
    assert "sync_next_vaccination_appointment_from_record" in appointment_block
    assert 'const [administeredDate, administeredTime = "00:00:00"]' in native_form
    assert "`${dueDate} ${administeredTime.slice(0, 8)}`" in native_form


def test_legacy_date_only_generated_appointments_keep_backward_compatibility():
    appointment_flow = read("vetedge/services/appointment_flow.py")

    assert 'DEFAULT_GENERATED_APPOINTMENT_TIME = "09:00:00"' in appointment_flow
    assert "if len(text) <= 10:" in appointment_flow
    assert "return get_datetime(value)" in appointment_flow
