from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return ROOT.joinpath(relative_path).read_text(encoding="utf-8")


def test_modal_update_repairs_invalid_stored_draft_due_date_before_billing_sync():
    content = read("vetedge/services/billing_context_alignment.py")

    assert "def _safe_due_date_for_posting(invoice, posting_date: str) -> str:" in content
    assert "def _prepare_active_billing_draft_dates(source_doctype: str, source_name: str) -> None:" in content
    assert 'if cint(invoice.get("docstatus")) != 0:' in content
    assert 'invoice.check_permission("write")' in content
    assert "target_posting_date = nowdate()" in content
    assert "target_due_date = _safe_due_date_for_posting(invoice, target_posting_date)" in content
    assert '"Sales Invoice",' in content
    assert '"due_date",' in content
    assert "target_due_date," in content
    assert "update_modified=False" in content

    method = content.split("def create_or_update_modal_invoice", 1)[1].split("def submit_modal_invoice", 1)[0]
    assert "_prepare_active_billing_draft_dates(source_doctype, source_name)" in method
    assert method.index("_prepare_active_billing_draft_dates") < method.index("original(source_doctype=source_doctype, source_name=source_name)")


def test_due_date_repair_uses_erpnext_terms_and_keeps_authorization_guards():
    content = read("vetedge/services/billing_context_alignment.py")
    due_block = content.split("def _safe_due_date_for_posting", 1)[1].split("def _prepare_active_billing_draft_dates", 1)[0]
    repair_block = content.split("def _prepare_active_billing_draft_dates", 1)[1].split("@frappe.whitelist()", 1)[0]

    assert "from erpnext.accounts.party import get_due_date" in due_block
    assert '"Customer",' in due_block
    assert 'template_name=invoice.get("payment_terms_template")' in due_block
    assert "get_billing_source_config" in repair_block
    assert "assert_can_act_on_source(source_doc, config)" in repair_block
    assert "require_vetedge_platform_access(" in repair_block
    assert 'action="create_or_update_modal_invoice"' in repair_block
    assert 'invoice.check_permission("write")' in repair_block
    assert "ignore_permissions" not in repair_block
    assert "db_set" not in repair_block
    assert 'cint(invoice.get("docstatus")) != 0' in repair_block
    assert "frappe.db.set_value(" in repair_block
