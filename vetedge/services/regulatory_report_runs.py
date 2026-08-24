from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import cstr, now_datetime
from frappe.utils.file_manager import save_file

from vetedge.services.platform_access import require_vetedge_platform_access
from vetedge.services.portal_access import require_internal_user

REPORT_RUN_DOCTYPE = "Veterinary Regulatory Report Run"
VACCINATION_REPORT = "NADIS Monthly Vaccination Report"
OUTBREAK_REPORT = "NADIS Disease Outbreak Report"
SUPPORTED_REPORTS = {VACCINATION_REPORT, OUTBREAK_REPORT}
ADMIN_ROLES = {"System Manager", "VetEdge Administrator"}
ALLOWED_SUBMISSION_STATUSES = {"Generated", "Sent", "Accepted", "Rejected", "Superseded"}


def _require_admin() -> None:
    require_internal_user()
    roles = set(frappe.get_roles(frappe.session.user) or [])
    if not roles.intersection(ADMIN_ROLES):
        frappe.throw(_("Regulatory report history is currently restricted to Veterinary administrators."), frappe.PermissionError)


def _parse_filters(filters: str | dict | None) -> dict:
    if not filters:
        return {}
    if isinstance(filters, dict):
        return dict(filters)
    parsed = frappe.parse_json(filters)
    if not isinstance(parsed, dict):
        frappe.throw(_("Expected regulatory report filters as a JSON object."), frappe.ValidationError)
    return parsed


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


def _assert_report_run_access(doc) -> None:
    if not doc.has_permission("read"):
        frappe.throw(_("You do not have permission to access this regulatory report run."), frappe.PermissionError)


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
    report_filters = _parse_filters(filters)
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
def update_regulatory_submission_status(
    name: str,
    status: str,
    submission_reference: str | None = None,
    notes: str | None = None,
) -> dict:
    _require_admin()
    name = cstr(name).strip()
    status = cstr(status).strip()
    if status not in ALLOWED_SUBMISSION_STATUSES:
        frappe.throw(_("Unsupported regulatory submission status."), frappe.ValidationError)
    if not name or not frappe.db.exists(REPORT_RUN_DOCTYPE, name):
        frappe.throw(_("Regulatory report run could not be found."), frappe.DoesNotExistError)

    require_vetedge_platform_access(
        action="update_regulatory_submission_status",
        reference_doctype=REPORT_RUN_DOCTYPE,
        reference_name=name,
    )
    run = frappe.get_doc(REPORT_RUN_DOCTYPE, name)
    run.check_permission("write")
    if status == "Generated" and run.status != "Generated":
        frappe.throw(_("A submitted regulatory report cannot be reset to Generated."), frappe.ValidationError)
    if status == "Sent" and not run.sent_on:
        frappe.throw(_("Use the explicit send action to mark a regulatory report as Sent."), frappe.ValidationError)
    run.status = status
    if submission_reference is not None:
        run.submission_reference = cstr(submission_reference).strip()
    if notes is not None:
        run.notes = cstr(notes)
    run.save()
    return {
        "name": run.name,
        "status": run.status,
        "submission_reference": run.submission_reference,
        "notes": run.notes,
    }
