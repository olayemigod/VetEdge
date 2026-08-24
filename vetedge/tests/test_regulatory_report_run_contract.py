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


def test_generation_uses_normalized_validated_data_and_private_file_attachment():
    service = (ROOT / "services/regulatory_report_runs.py").read_text(encoding="utf-8")

    for expected in (
        'generate_regulatory_report_run',
        'require_vetedge_platform_access(',
        'action="generate_regulatory_report_run"',
        '_normalize_effective_filters(report_type, raw_filters)',
        '_official_rows(filters)',
        '_dataset(filters)',
        'if not result["submission_ready"]',
        'save_file(',
        'is_private=1',
        'run.template_sha256 = payload["template_sha256"]',
        'run.generated_by = frappe.session.user',
        'run.generated_on = now_datetime()',
        'run.flags.vetedge_regulatory_generation_action = True',
        'run.db_set("export_file", file_doc.file_url, update_modified=False)',
        '"effective_filters": report_filters',
    ):
        assert expected in service

    for forbidden in (
        "ignore_permissions=True",
        "ignore_permissions=1",
        ".submit()",
        ".cancel()",
        'frappe.db.set_value("Sales Invoice"',
        'frappe.db.set_value("Payment Entry"',
        'frappe.db.set_value("Stock Entry"',
    ):
        assert forbidden not in service


def test_report_run_controller_rejects_manual_creation_and_evidence_changes():
    controller = (ROOT / "veterinary/doctype/veterinary_regulatory_report_run/veterinary_regulatory_report_run.py").read_text(encoding="utf-8")

    for expected in (
        'if not self.flags.get("vetedge_regulatory_generation_action")',
        'Regulatory Report Runs must be created from the Regulatory Reporting Generate & Save action.',
        'self.export_file = None',
        'GENERATED_EVIDENCE_FIELDS = (',
        'Generated regulatory evidence field {0} cannot be changed after the report run is created.',
        'if previous_file != current_file',
        'The generated regulatory workbook attachment cannot be changed from the Report Run form.',
    ):
        assert expected in controller


def test_regulatory_report_history_is_bounded_and_admin_only():
    service = (ROOT / "services/regulatory_report_runs.py").read_text(encoding="utf-8")

    assert 'ADMIN_ROLES = {"System Manager", "VetEdge Administrator"}' in service
    assert 'page_length = min(max(int(page_length or 25), 1), 100)' in service
    assert 'order_by="generated_on desc, name desc"' in service
    assert '"has_next": start + len(rows) < total' in service


def test_send_uses_frozen_private_attachment_and_does_not_regenerate_report():
    service = (ROOT / "services/regulatory_report_runs.py").read_text(encoding="utf-8")
    send_section = service.split("def send_regulatory_report_run", 1)[1].split("def update_regulatory_submission_status", 1)[0]

    for expected in (
        'action="send_regulatory_report_run"',
        '_get_attached_file(run)',
        'attachment_content = file_doc.get_content()',
        'attachments=[{"fname": file_doc.file_name, "fcontent": attachment_content}]',
        'now=True',
        'run.status = "Sent"',
        'run.sent_to = ", ".join(recipient_list)',
        'run.sent_on = sent_on',
        'run.flags.vetedge_regulatory_send_action = True',
        'Accepted or Superseded regulatory reports cannot be emailed again.',
    ):
        assert expected in send_section

    for forbidden in (
        "_official_rows(",
        "_dataset(",
        "_build_workbook(",
        "save_file(",
    ):
        assert forbidden not in send_section


def test_recipient_validation_is_bounded():
    service = (ROOT / "services/regulatory_report_runs.py").read_text(encoding="utf-8")

    for expected in (
        "MAX_EMAIL_RECIPIENTS = 20",
        "validate_email_address(address, throw=True)",
        "Enter at least one valid email recipient.",
        "A regulatory report can be sent to at most {0} recipients at once.",
    ):
        assert expected in service


def test_submission_status_cannot_fake_sent_or_skip_send_state():
    service = (ROOT / "services/regulatory_report_runs.py").read_text(encoding="utf-8")
    controller = (ROOT / "veterinary/doctype/veterinary_regulatory_report_run/veterinary_regulatory_report_run.py").read_text(encoding="utf-8")

    for expected in (
        'if status == "Generated" and run.status != "Generated"',
        'if status == "Sent" and not run.sent_on',
        'Use the explicit send action to mark a regulatory report as Sent.',
        'status in {"Accepted", "Rejected"} and run.status not in {"Sent", "Accepted", "Rejected"}',
        'A regulatory report must be Sent before it can be marked Accepted or Rejected.',
        'run.flags.vetedge_regulatory_status_action = True',
        'action="update_regulatory_submission_status"',
    ):
        assert expected in service

    for expected in (
        'self.flags.get("vetedge_regulatory_send_action")',
        'self.flags.get("vetedge_regulatory_status_action")',
        'Use the Regulatory Reporting send action to mark a report as Sent.',
        'Use the Regulatory Reporting status action to change submission status.',
    ):
        assert expected in controller
