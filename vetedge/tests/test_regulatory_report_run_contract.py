from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_regulatory_report_run_captures_generation_and_submission_evidence():
    doctype = (ROOT / "veterinary/doctype/veterinary_regulatory_report_run/veterinary_regulatory_report_run.json").read_text(encoding="utf-8")

    for expected in (
        '"name": "Veterinary Regulatory Report Run"',
        '"fieldname": "report_type"',
        '"fieldname": "status"',
        '"fieldname": "company"',
        '"fieldname": "service_branch"',
        '"fieldname": "from_date"',
        '"fieldname": "to_date"',
        '"fieldname": "generated_on"',
        '"fieldname": "generated_by"',
        '"fieldname": "template_sha256"',
        '"fieldname": "source_count"',
        '"fieldname": "output_row_count"',
        '"fieldname": "warning_count"',
        '"fieldname": "export_file"',
        '"fieldname": "sent_to"',
        '"fieldname": "sent_on"',
        '"fieldname": "submission_reference"',
        'Generated\\nSent\\nAccepted\\nRejected\\nSuperseded',
    ):
        assert expected in doctype


def test_generation_uses_validated_report_data_and_private_file_attachment():
    service = (ROOT / "services/regulatory_report_runs.py").read_text(encoding="utf-8")

    for expected in (
        'generate_regulatory_report_run',
        'require_vetedge_platform_access(',
        'action="generate_regulatory_report_run"',
        '_official_rows(filters)',
        '_dataset(filters)',
        'if not result["submission_ready"]',
        'save_file(',
        'is_private=1',
        'run.template_sha256 = payload["template_sha256"]',
        'run.generated_by = frappe.session.user',
        'run.generated_on = now_datetime()',
        'run.db_set("export_file", file_doc.file_url, update_modified=False)',
    ):
        assert expected in service

    for forbidden in (
        "ignore_permissions=True",
        "ignore_permissions=1",
        ".submit()",
        ".cancel()",
        "frappe.db.set_value(\"Sales Invoice\"",
        "frappe.db.set_value(\"Payment Entry\"",
        "frappe.db.set_value(\"Stock Entry\"",
    ):
        assert forbidden not in service


def test_regulatory_report_history_is_bounded_and_admin_only():
    service = (ROOT / "services/regulatory_report_runs.py").read_text(encoding="utf-8")

    assert 'ADMIN_ROLES = {"System Manager", "VetEdge Administrator"}' in service
    assert 'page_length = min(max(int(page_length or 25), 1), 100)' in service
    assert 'order_by="generated_on desc, name desc"' in service
    assert '"has_next": start + len(rows) < total' in service


def test_submission_status_cannot_fake_sent_state():
    service = (ROOT / "services/regulatory_report_runs.py").read_text(encoding="utf-8")

    for expected in (
        'if status == "Generated" and run.status != "Generated"',
        'if status == "Sent" and not run.sent_on',
        'Use the explicit send action to mark a regulatory report as Sent.',
        'action="update_regulatory_submission_status"',
    ):
        assert expected in service
