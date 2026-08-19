from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def function_block(source: str, name: str) -> str:
    marker = f"def {name}("
    start = source.index(marker)
    next_def = source.find("\ndef ", start + len(marker))
    next_whitelisted = source.find("\n@frappe.whitelist()", start + len(marker))
    candidates = [index for index in (next_def, next_whitelisted) if index >= 0]
    end = min(candidates) if candidates else len(source)
    return source[start:end]


def test_vaccination_notification_hydration_uses_real_datetime_field():
    source = read("vetedge/services/notifications.py")
    start = source.index('"Veterinary Vaccination Record": (')
    end = source.index("),", start) + 2
    vaccination_fields = source[start:end]

    assert '"administered_on"' in vaccination_fields
    assert '"vaccination_date"' not in vaccination_fields


def test_vaccination_stock_control_uses_existing_dispensary_feature_flag():
    source = read("vetedge/services/vaccination.py")
    helper = function_block(source, "is_vaccination_stock_control_enabled")

    assert 'frappe.db.exists("DocType", "Veterinary Settings")' in helper
    assert 'return is_enabled("dispensary_flow")' in helper


def test_vaccination_batch_validation_is_disabled_with_dispensary_flow():
    source = read("vetedge/services/vaccination.py")
    block = function_block(source, "validate_stock_batch")

    gate = 'if not is_vaccination_stock_control_enabled():\n\t\treturn'
    assert gate in block
    assert block.index(gate) < block.index("get_vaccine_defaults")
    assert 'frappe.db.get_value("Batch"' in block


def test_vaccination_stock_entry_is_disabled_with_dispensary_flow():
    source = read("vetedge/services/vaccination.py")
    block = function_block(source, "create_vaccination_stock_entry")

    gate = 'if not is_vaccination_stock_control_enabled():\n\t\treturn None'
    assert gate in block
    assert block.index(gate) < block.index("get_vaccine_defaults")
    assert "validate_stock_availability" in block
    assert '"stock_entry_type": "Material Issue"' in block
    assert "entry.submit()" in block


def test_vaccination_clinical_and_billing_flow_remain_independent_of_dispensary():
    source = read("vetedge/services/vaccination.py")
    finalize = function_block(source, "finalize_administered_vaccination")

    assert "calculate_next_due_date(doc)" in finalize
    assert "create_vaccination_stock_entry(doc)" in finalize
    assert "create_vaccination_invoice(doc)" in finalize
    assert "doc.save()" in finalize
    assert '"vaccination_administered"' in finalize
