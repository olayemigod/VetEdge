from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return ROOT.joinpath(relative_path).read_text(encoding="utf-8")


def test_modal_wrapper_does_not_mutate_sales_invoice_dates_before_billing_sync():
    content = read("vetedge/services/billing_context_alignment.py")

    assert "_prepare_active_billing_draft_dates" not in content
    assert "_safe_due_date_for_posting" not in content
    assert 'frappe.db.set_value(\n        "Sales Invoice"' not in content

    method = content.split("def create_or_update_modal_invoice", 1)[1].split("def submit_modal_invoice", 1)[0]
    assert "billing_state_security import create_or_update_modal_invoice as original" in method
    assert "return _normalize_payload(original(source_doctype=source_doctype, source_name=source_name))" in method


def test_billing_core_submit_path_keeps_existing_posting_time_safeguard():
    content = read("vetedge/services/billing_core.py")
    block = content.split("def prepare_vetedge_invoice_for_submit", 1)[1].split("def invoice_has_field", 1)[0]

    assert 'invoice_has_field(invoice, "set_posting_time")' in block
    assert "invoice.set_posting_time = 1" in block
    assert "invoice.posting_date = nowdate()" in block
