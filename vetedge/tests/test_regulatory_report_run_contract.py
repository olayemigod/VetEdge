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
        'assert_transition(',
    ):
        assert expected in controller


def test_regulatory_report_history_is_bounded_and_admin_only():
    service = (ROOT / "services/regulatory_report_runs.py").read_text(encoding="utf-8")

    assert 'ADMIN_ROLES = {"System Manager", "VetEdge Administrator"}' in service
    assert 'page_length = min(max(int(page_length or 25), 1), 100)' in service
    assert 'order_by="generated_on desc, name desc"' in service
    assert '"has_next": start + len(rows) < total' in service


def test_send_uses_frozen_private_attachment_and_confirms_delivery_before_sent_state():
    service = (ROOT / "services/regulatory_report_runs.py").read_text(encoding="utf-8")
    send_section = service.split("def send_regulatory_report_run", 1)[1].split("def update_regulatory_submission_status", 1)[0]

    for expected in (
        'action="send_regulatory_report_run"',
        'assert_sendable(cstr(run.status).strip())',
        '_get_attached_file(run)',
        'attachment_content = file_doc.get_content()',
        'assert_transition(cstr(run.status).strip(), "Sent", has_sent_evidence=True)',
        'attachments=[{"fname": file_doc.file_name, "fcontent": attachment_content}]',
        'reference_doctype=REPORT_RUN_DOCTYPE',
        'reference_name=run.name',
        'now=False',
        'email_queue.send()',
        '_sent_queue_recipients(email_queue)',
        'cstr(email_queue.status).strip() != "Sent"',
        'The regulatory report remains Generated.',
        'run.status = "Sent"',
        'run.sent_to = ", ".join(sent_recipients)',
        'run.sent_on = sent_on',
        'run.flags.vetedge_regulatory_send_action = True',
    ):
        assert expected in send_section

    assert 'now=True,' not in send_section
    assert send_section.index('assert_sendable(cstr(run.status).strip())') < send_section.index('frappe.sendmail(')
    assert send_section.index('assert_transition(cstr(run.status).strip(), "Sent", has_sent_evidence=True)') < send_section.index('frappe.sendmail(')
    assert send_section.index('email_queue.send()') < send_section.index('run.status = "Sent"')
    assert send_section.index('cstr(email_queue.status).strip() != "Sent"') < send_section.index('run.status = "Sent"')

    for forbidden in (
        "_official_rows(",
        "_dataset(",
        "_build_workbook(",
        "save_file(",
    ):
        assert forbidden not in send_section


def test_send_preserves_partial_delivery_evidence_in_linked_email_queue():
    service = (ROOT / "services/regulatory_report_runs.py").read_text(encoding="utf-8")
    send_section = service.split("def send_regulatory_report_run", 1)[1].split("def update_regulatory_submission_status", 1)[0]

    for expected in (
        'except Exception:',
        'sent_recipients = _sent_queue_recipients(email_queue)',
        'Email delivery was only partially successful.',
        'Frappe confirmed delivery to: {0}.',
        'Review the linked Email Queue before retrying.',
    ):
        assert expected in send_section

    helper_section = service.split("def _sent_queue_recipients", 1)[1].split("@frappe.whitelist()", 1)[0]
    assert 'email_queue.reload()' in helper_section
    assert 'cstr(row.status).strip() == "Sent"' in helper_section


def test_recipient_validation_is_bounded():
    service = (ROOT / "services/regulatory_report_runs.py").read_text(encoding="utf-8")

    for expected in (
        "MAX_EMAIL_RECIPIENTS = 20",
        "validate_email_address(address, throw=True)",
        "Enter at least one valid email recipient.",
        "A regulatory report can be sent to at most {0} recipients at once.",
    ):
        assert expected in service


def test_submission_status_uses_shared_state_machine():
    service = (ROOT / "services/regulatory_report_runs.py").read_text(encoding="utf-8")
    controller = (ROOT / "veterinary/doctype/veterinary_regulatory_report_run/veterinary_regulatory_report_run.py").read_text(encoding="utf-8")
    state = (ROOT / "services/regulatory_report_state.py").read_text(encoding="utf-8")

    for expected in (
        'from vetedge.services.regulatory_report_state import assert_sendable, assert_transition',
        'run.flags.vetedge_regulatory_status_action = True',
        'action="update_regulatory_submission_status"',
        'assert_transition(',
    ):
        assert expected in service

    for expected in (
        'from vetedge.services.regulatory_report_state import assert_transition',
        'self.flags.get("vetedge_regulatory_send_action")',
        'self.flags.get("vetedge_regulatory_status_action")',
        'Use the Regulatory Reporting send action to mark a report as Sent.',
        'Use the Regulatory Reporting status action to change submission status.',
        'assert_transition(',
    ):
        assert expected in controller

    for expected in (
        'SENDABLE_STATUSES = {"Generated"}',
        'FINAL_STATUSES = {"Accepted", "Superseded"}',
        'Rejected reports must be corrected, regenerated, and then marked Superseded.',
        'Only a Sent regulatory report can be marked Accepted or Rejected.',
    ):
        assert expected in state
