import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return ROOT.joinpath(relative_path).read_text(encoding="utf-8")


def read_json(relative_path: str) -> dict:
    return json.loads(read(relative_path))


def field(meta: dict, fieldname: str) -> dict:
    return next(row for row in meta["fields"] if row.get("fieldname") == fieldname)


def test_every_consultation_treatment_row_requires_an_erpnext_item():
    treatment_meta = read_json(
        "vetedge/veterinary/doctype/planned_treatment_item/planned_treatment_item.json"
    )
    item = field(treatment_meta, "item")
    assert item["fieldtype"] == "Link"
    assert item["options"] == "Item"
    assert item["reqd"] == 1

    controller = read(
        "vetedge/veterinary/doctype/veterinary_consultation/veterinary_consultation.py"
    )
    assert "validate_treatment_rows_have_erpnext_item(self)" in controller
    assert 'if row.get("item"):' in controller
    assert "ERPNext Item is required for Treatment Plan row" in controller

    plan = read("vetedge/services/consultation_billing_plan.py")
    assert "if not item:" in plan
    assert "ERPNext Item is required for every Consultation Treatment Plan row." in plan


def test_lab_test_master_and_lab_order_require_erpnext_item_but_allow_zero_rate():
    meta = read_json(
        "vetedge/veterinary/doctype/veterinary_lab_test/veterinary_lab_test.json"
    )
    linked_item = field(meta, "linked_item")
    assert linked_item["fieldtype"] == "Link"
    assert linked_item["options"] == "Item"
    assert linked_item["reqd"] == 1

    master_controller = read(
        "vetedge/veterinary/doctype/veterinary_lab_test/veterinary_lab_test.py"
    )
    assert 'if not self.get("linked_item"):' in master_controller
    assert "Every Veterinary Lab Test must map to an ERPNext Item" in master_controller

    order_controller = read(
        "vetedge/veterinary/doctype/veterinary_lab_order/veterinary_lab_order.py"
    )
    assert 'if not row.get("billing_item"):' in order_controller
    assert "has no ERPNext billing Item" in order_controller

    lab_service = read("vetedge/services/lab.py")
    assert 'if row.get("rate") not in (None, "") and flt(row.get("rate")) < 0:' in lab_service
    assert 'if not row.billing_item and lab_test.linked_item:' in lab_service


def test_vaccine_master_and_vaccination_require_erpnext_item_but_rate_can_be_zero():
    meta = read_json(
        "vetedge/veterinary/doctype/veterinary_vaccine/veterinary_vaccine.json"
    )
    default_item = field(meta, "default_item")
    assert default_item["fieldtype"] == "Link"
    assert default_item["options"] == "Item"
    assert default_item["reqd"] == 1

    master_controller = read(
        "vetedge/veterinary/doctype/veterinary_vaccine/veterinary_vaccine.py"
    )
    assert 'if not self.get("default_item"):' in master_controller
    assert "Every Veterinary Vaccine must map to an ERPNext Item" in master_controller

    record_controller = read(
        "vetedge/veterinary/doctype/veterinary_vaccination_record/veterinary_vaccination_record.py"
    )
    assert 'if not self.get("billing_item"):' in record_controller
    assert "has no ERPNext billing Item" in record_controller

    vaccination = read("vetedge/services/vaccination.py")
    assert '"rate": rate' in vaccination
    assert 'rate = 0' in vaccination


def test_source_generated_consultation_rows_only_allow_rate_override():
    backend = read("vetedge/services/clinical_workspace_stage3.py")
    assert 'SOURCE_BILLING_EDITABLE_FIELDS = {"rate"}' in backend
    assert "The ERPNext Item remains fixed by the clinical master" in backend
    assert '"item": existing.get("item")' in backend
    assert '"rate": flt(incoming.get("rate"))' in backend

    vue = read(
        "vetedge/public/js/vetedge_clinical_workspace/VetEdgeClinicalWorkspace.vue"
    )
    assert ":disabled=\"treatmentFieldLocked(row, 'item')\"" in vue
    assert ":disabled=\"treatmentFieldLocked(row, 'rate')\"" in vue
    assert "return field !== 'rate' || !this.sourceTreatmentRateEditable(row);" in vue
    assert "ERPNext Item for Lab/Vaccination rows is fixed by its clinical master" in vue
    assert "allow_editing_vaccination_billing" in vue


def test_consultation_related_popups_use_business_names_rates_and_safe_delete():
    bundle = read("vetedge/public/js/vetedge_clinical_workspace.bundle.js")
    assert "{ fieldname: 'display_name', label: 'Lab Tests' }" in bundle
    assert "{ fieldname: 'display_name', label: 'Vaccination' }" in bundle
    assert "get_consultation_related_records" in bundle
    assert "delete_consultation_related_record" in bundle
    assert "create_consultation_lab_order" in bundle
    assert "ERPNext Item required" in bundle
    assert "lab_test_rate_" in bundle
    assert "rate: Number(nextValues[row.rateField]" in bundle
    assert "submitted or paid accounting records" in bundle.lower()

    backend = read("vetedge/services/consultation_related_records.py")
    assert '"display_name": ", ".join(tests)' in backend
    assert '"display_name": vaccine_map.get' in backend
    assert "This record is on a submitted Sales Invoice and cannot be deleted" in backend
    assert "This service has finalized billing and cannot be deleted" in backend
    assert "validate_consultation_lab_test_duplicates" in backend
    assert "validate_consultation_vaccination_duplicate" in backend


def test_duplicate_lab_test_and_vaccine_are_server_enforced_per_consultation():
    lab_controller = read(
        "vetedge/veterinary/doctype/veterinary_lab_order/veterinary_lab_order.py"
    )
    vaccination_controller = read(
        "vetedge/veterinary/doctype/veterinary_vaccination_record/veterinary_vaccination_record.py"
    )
    backend = read("vetedge/services/consultation_related_records.py")

    assert "validate_consultation_lab_test_duplicates(self)" in lab_controller
    assert "validate_consultation_vaccination_duplicate(self)" in vaccination_controller
    assert "is already active on this Consultation" in backend
    assert '"status": ["!=", "Cancelled"]' in backend


def test_vaccination_rate_edit_policy_is_settings_driven_and_migrated():
    patch = read("vetedge/patches/add_vaccination_consultation_billing_edit_setting.py")
    patches = read("vetedge/patches.txt")
    backend = read("vetedge/services/consultation_related_records.py")

    assert 'FIELDNAME = "allow_vaccination_billing_edit_in_consultation"' in patch
    assert '"label": "Allow Vaccination Rate Edits in Consultation"' in patch
    assert '"default": "1"' in patch
    assert "The ERPNext Item remains fixed by the Vaccine" in patch
    assert "vetedge.patches.add_vaccination_consultation_billing_edit_setting" in patches
    assert "vaccination_billing_edit_is_enabled()" in backend
