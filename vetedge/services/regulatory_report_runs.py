from __future__ import annotations

import re
from typing import Any

import frappe
from frappe import _
from frappe.utils import cstr, now_datetime, validate_email_address
from frappe.utils.file_manager import save_file

from vetedge.services.platform_access import require_vetedge_platform_access
from vetedge.services.portal_access import require_internal_user

REPORT_RUN_DOCTYPE = "Veterinary Regulatory Report Run"
VACCINATION_REPORT = "NADIS Monthly Vaccination Report"
OUTBREAK_REPORT = "NADIS Disease Outbreak Report"
SUPPORTED_REPORTS = {VACCINATION_REPORT, OUTBREAK_REPORT}
ADMIN_ROLES = {"System Manager", "VetEdge Administrator"}
ALLOWED_SUBMISSION_STATUSES = {"Generated", "Sent", "Accepted", "Rejected", "Superseded"}
MAX_EMAIL_RECIPIENTS = 20


def _require_admin() -> None:
    require_internal_user()
    roles = set(frappe.get_roles(frappe.session.user) or [])
    if not roles.intersection(ADMIN_ROLES):
        frappe.throw(
            _("Regulatory report history is currently restricted to Veterinary administrators."),
            frappe.PermissionError,
        )


def _parse_filters(filters: str | dict | None) -> dict:
    if not filters:
        return {}
    if isinstance(filters, dict):
        return dict(filters)
    parsed = frappe.parse_json(filters)
    if not isinstance(parsed, dict):
        frappe.throw(_("Expected regulatory report filters as a JSON object."), frappe.ValidationError)
    return parsed


def _normalize_effective_filters(report_type: str, filters: dict) -> dict:
    if report_type == VACCINATION_REPORT:
        from vetedge.services.nadis_reporting import _filters as normalize

        return dict(normalize(filters) or {})
    if report_type == OUTBREAK_REPORT:
        from vetedge.services.nadis_outbreak_export import _filters as normalize

        return dict(normalize(filters) or {})
    frappe.throw(_("Unsupported regulatory report type."), frappe.ValidationError)


def _report_payload(report_type: str, filters: dict) -> dict[str, Any]:
    if report_type == VACCINATION_REPORT:
        from vetedge.services.nadis_vaccination_export import _build_workbook, _export_filename, _official_rows

        result = _official_rows(filters)
        if not result["submission_ready"]:
            messages = [item.get("message") for item in result["errors"][:10]]
            frappe.throw(
                _("Vaccination regulatory report is not ready to generate.{0}").format(
                    "\n" + "\n".join(messages) if messages else ""
                ),
                frappe.ValidationError,
            )
        return {
            "filename": _export_filename(filters),
            "content": _build_workbook(result["rows"]),
            "template_filename": result["template_filename"],
            "template_sha256": result["template_sha256"],
            "source_count": result["source_count"],
            "output_row_count": len(result["rows"]),
            "warning_count": len(result["warnings"]),
        }

    if report_type == OUTBREAK_REPORT:
        from vetedge.services.nadis_outbreak_export import _build_workbook, _dataset

        result = _dataset(filters)
        if not result["submission_ready"]:
            messages = [item.get("message") for item in result["errors"][:10]]
            frappe.throw(
                _("Disease Outbreak regulatory report is not ready to generate.{0}").format(
                    "\n" + "\n".join(messages) if messages else ""
                ),
                frappe.ValidationError,
            )
        from_date = cstr(filters.get("from_date")).strip()
        to_date = cstr(filters.get("to_date")).strip()
        suffix = ""
        if from_date or to_date:
            suffix = "_" + "_to_".join(value for value in (from_date, to_date) if value)
        return {
            "filename": f"NADIS_Disease_Outbreak_Report{suffix}.xlsx",
            "content": _build_workbook(result),
            "template_filename": result["template_filename"],
            "template_sha256": result["template_sha256"],
            "source_count": len(result["parents"]),
            "output_row_count": sum(
                len(result[key])
                for key in ("parents", "animals", "diagnoses", "controls", "locations")
            ),
            "warning_count": len(result["warnings"]),
        }

    frappe.throw(_("Unsupported regulatory report type."), frappe.ValidationError)


def _get_report_run(name: str, permission_type: str = "read"):
    name = cstr(name).strip()
    if not name or not frappe.db.exists(REPORT_RUN_DOCTYPE, name):
        frappe.throw(_("Regulatory report run could not be found."), frappe.DoesNotExistError)
    run = frappe.get_doc(REPORT_RUN_DOCTYPE, name)
    run.check_permission(permission_type)
    return run


def _get_attached_file(run):
    if not run.export_file:
        frappe.throw(_("This regulatory report run does not have a generated workbook attachment."), frappe.ValidationError)
    file_name = frappe.db.get_value(
        "File",
        {
            "attached_to_doctype": REPORT_RUN_DOCTYPE,
            "attached_to_name": run.name,
            "file_url": run.export_file,
        },
        "name",
    )
    if not file_name:
        frappe.throw(_("The generated regulatory workbook attachment could not be found."), frappe.DoesNotExistError)
    file_doc = frappe.get_doc("File", file_name)
    file_doc.check_permission("read")
    return file_doc


def _parse_recipients(value: str | list[str] | tuple[str, ...]) -> list[str]:
    if isinstance(value, (list, tuple)):
        candidates = value
    else:
        candidates = re.split(r"[,;\n]+", cstr(value))
    recipients = []
    seen = set()
    for candidate in candidates:
        address = cstr(candidate).strip()
        if not address:
            continue
        validate_email_address(address, throw=True)
        key = address.lower()
        if key not in seen:
            seen.add(key)
            recipients.append(address)
    if not recipients:
        frappe.throw(_("Enter at least one valid email recipient."), frappe.ValidationError)
    if len(recipients) > MAX_EMAIL_RECIPIENTS:
        frappe.throw(
            _("A regulatory report can be sent to at most {0} recipients at once.").format(MAX_EMAIL_RECIPIENTS),
            frappe.ValidationError,
        )
    return recipients


@frappe.whitelist()
def generate_regulatory_report_run(report_type: str, filters: str | dict | None = None) -> dict:
    _require_admin()
    report_type = cstr(report_type).strip()
    if report_type not in SUPPORTED_REPORTS:
        frappe.throw(_("Unsupported regulatory report type."), frappe.ValidationError)

    require_vetedge_platform_access(
        action="generate_regulatory_report_run",
        reference_doctype=REPORT_RUN_DOCTYPE,
    )
    raw_filters = _parse_filters(filters)
    report_filters = _normalize_effective_filters(report_type, raw_filters)
    if raw_filters.get("company") and not report_filters.get("company"):
        report_filters["company"] = raw_filters["company"]
    payload = _report_payload(report_type, report_filters)

    run = frappe.new_doc(REPORT_RUN_DOCTYPE)
    run.report_type = report_type
    run.status = "Generated"
    run.company = report_filters.get("company") or frappe.defaults.get_user_default("Company")
    run.service_branch = report_filters.get("branch") or frappe.defaults.get_user_default("branch")
    run.from_date = report_filters.get("from_date") or None
    run.to_date = report_filters.get("to_date") or None
    run.generated_on = now_datetime()
    run.generated_by = frappe.session.user
    run.template_filename = payload["template_filename"]
    run.template_sha256 = payload["template_sha256"]
    run.source_count = payload["source_count"]
    run.output_row_count = payload["output_row_count"]
    run.warning_count = payload["warning_count"]
    run.insert()

    file_doc = save_file(
        payload["filename"],
        payload["content"],
        REPORT_RUN_DOCTYPE,
        run.name,
        is_private=1,
    )
    run.db_set("export_file", file_doc.file_url, update_modified=False)

    return {
        "name": run.name,
        "report_type": run.report_type,
        "status": run.status,
        "company": run.company,
        "branch": run.service_branch,
        "from_date": run.from_date,
        "to_date": run.to_date,
        "generated_on": run.generated_on,
        "generated_by": run.generated_by,
        "template_filename": run.template_filename,
        "template_sha256": run.template_sha256,
        "source_count": run.source_count,
        "output_row_count": run.output_row_count,
        "warning_count": run.warning_count,
        "file_url": file_doc.file_url,
        "effective_filters": report_filters,
    }


@frappe.whitelist()
@frappe.read_only()
def get_regulatory_report_runs(
    report_type: str | None = None,
    company: str | None = None,
    branch: str | None = None,
    status: str | None = None,
    start: int = 0,
    page_length: int = 25,
) -> dict:
    _require_admin()
    filters = {}
    if report_type:
        filters["report_type"] = cstr(report_type).strip()
    if company:
        filters["company"] = cstr(company).strip()
    if branch:
        filters["service_branch"] = cstr(branch).strip()
    if status:
        filters["status"] = cstr(status).strip()
    start = max(int(start or 0), 0)
    page_length = min(max(int(page_length or 25), 1), 100)
    total = frappe.db.count(REPORT_RUN_DOCTYPE, filters=filters)
    rows = frappe.get_list(
        REPORT_RUN_DOCTYPE,
        filters=filters,
        fields=[
            "name",
            "report_type",
            "status",
            "company",
            "service_branch",
            "from_date",
            "to_date",
            "generated_on",
            "generated_by",
            "template_filename",
            "template_sha256",
            "source_count",
            "output_row_count",
            "warning_count",
            "export_file",
            "sent_to",
            "sent_on",
            "submission_reference",
        ],
        order_by="generated_on desc, name desc",
        start=start,
        page_length=page_length,
    )
    return {
        "rows": rows,
        "total": total,
        "start": start,
        "page_length": page_length,
        "has_previous": start > 0,
        "has_next": start + len(rows) < total,
    }


@frappe.whitelist()
def send_regulatory_report_run(
    name: str,
    recipients: str | list[str],
    subject: str | None = None,
    message: str | None = None,
) -> dict:
    """Send the frozen workbook attached to an existing Report Run.

    The report is deliberately not regenerated here. This guarantees that the
    file emailed externally is the same file retained in VetEdge report history.
    """
    _require_admin()
    run = _get_report_run(name, "write")
    if run.status in {"Accepted", "Superseded"}:
        frappe.throw(
            _("Accepted or Superseded regulatory reports cannot be emailed again. Generate a new report if a replacement is required."),
            frappe.ValidationError,
        )
    require_vetedge_platform_access(
        action="send_regulatory_report_run",
        reference_doctype=REPORT_RUN_DOCTYPE,
        reference_name=run.name,
    )
    recipient_list = _parse_recipients(recipients)
    file_doc = _get_attached_file(run)
    attachment_content = file_doc.get_content()
    mail_subject = cstr(subject).strip() or _("{0} - {1}").format(run.report_type, run.name)
    mail_message = cstr(message).strip() or _(
        "Please find attached the Veterinary regulatory report generated from VetEdge."
    )

    frappe.sendmail(
        recipients=recipient_list,
        subject=mail_subject,
        message=mail_message,
        attachments=[{"fname": file_doc.file_name, "fcontent": attachment_content}],
        now=True,
    )

    sent_on = now_datetime()
    run.status = "Sent"
    run.sent_to = ", ".join(recipient_list)
    run.sent_on = sent_on
    run.flags.vetedge_regulatory_send_action = True
    run.save()
    return {
        "name": run.name,
        "status": run.status,
        "sent_to": run.sent_to,
        "sent_on": run.sent_on,
        "file_url": run.export_file,
    }


@frappe.whitelist()
def update_regulatory_submission_status(
    name: str,
    status: str,
    submission_reference: str | None = None,
    notes: str | None = None,
) -> dict:
    _require_admin()
    status = cstr(status).strip()
    if status not in ALLOWED_SUBMISSION_STATUSES:
        frappe.throw(_("Unsupported regulatory submission status."), frappe.ValidationError)

    run = _get_report_run(name, "write")
    require_vetedge_platform_access(
        action="update_regulatory_submission_status",
        reference_doctype=REPORT_RUN_DOCTYPE,
        reference_name=run.name,
    )
    if status == "Generated" and run.status != "Generated":
        frappe.throw(_("A submitted regulatory report cannot be reset to Generated."), frappe.ValidationError)
    if status == "Sent" and not run.sent_on:
        frappe.throw(_("Use the explicit send action to mark a regulatory report as Sent."), frappe.ValidationError)
    if status in {"Accepted", "Rejected"} and run.status not in {"Sent", "Accepted", "Rejected"}:
        frappe.throw(
            _("A regulatory report must be Sent before it can be marked Accepted or Rejected."),
            frappe.ValidationError,
        )
    run.status = status
    if submission_reference is not None:
        run.submission_reference = cstr(submission_reference).strip()
    if notes is not None:
        run.notes = cstr(notes)
    run.flags.vetedge_regulatory_status_action = True
    run.save()
    return {
        "name": run.name,
        "status": run.status,
        "submission_reference": run.submission_reference,
        "notes": run.notes,
    }
