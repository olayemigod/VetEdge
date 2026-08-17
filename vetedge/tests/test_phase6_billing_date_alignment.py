from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return ROOT.joinpath(relative_path).read_text(encoding="utf-8")


def test_modal_update_aligns_only_active_draft_dates_before_billing_sync():
    content = read("vetedge/services/billing_context_alignment.py")

    assert "def _prepare_active_billing_draft_dates(source_doctype: str, source_name: str) -> None:" in content
    assert 'if cint(invoice.get("docstatus")) != 0:' in content
    assert "target_posting_date = nowdate()" in content
    assert "invoice.posting_date = target_posting_date" in content
    assert "invoice.due_date = due_date" in content
    assert "invoice.save()" in content

    method = content.split("def create_or_update_modal_invoice", 1)[1].split("def submit_modal_invoice", 1)[0]
    assert "_prepare_active_billing_draft_dates(source_doctype, source_name)" in method
    assert method.index("_prepare_active_billing_draft_dates") < method.index("original(source_doctype=source_doctype, source_name=source_name)")


def test_date_alignment_does_not_add_permission_or_submitted_document_bypass():
    content = read("vetedge/services/billing_context_alignment.py")
    block = content.split("def _prepare_active_billing_draft_dates", 1)[1].split("@frappe.whitelist()", 1)[0]

    assert "ignore_permissions" not in block
    assert "db_set" not in block
    assert "frappe.db.set_value" not in block
    assert 'cint(invoice.get("docstatus")) != 0' in block
