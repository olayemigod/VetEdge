from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, now_datetime

from vetedge.services.regulatory_report_state import assert_transition

GENERATED_EVIDENCE_FIELDS = (
    "report_type",
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
)


class VeterinaryRegulatoryReportRun(Document):
    def before_insert(self):
        if not self.flags.get("vetedge_regulatory_generation_action"):
            frappe.throw(
                _("Regulatory Report Runs must be created from the Regulatory Reporting Generate & Save action."),
                frappe.PermissionError,
            )
        self.status = "Generated"
        self.generated_on = self.generated_on or now_datetime()
        self.generated_by = self.generated_by or frappe.session.user
        self.export_file = None

    def validate(self):
        self._protect_generation_evidence()
        self._validate_status_evidence()
        self._validate_controlled_status_transition()

    def _protect_generation_evidence(self):
        if self.is_new():
            return
        previous = self.get_doc_before_save()
        if not previous:
            return
        for fieldname in GENERATED_EVIDENCE_FIELDS:
            if previous.get(fieldname) != self.get(fieldname):
                frappe.throw(
                    _("Generated regulatory evidence field {0} cannot be changed after the report run is created.").format(
                        self.meta.get_label(fieldname)
                    ),
                    frappe.ValidationError,
                )
        previous_file = cstr(previous.get("export_file")).strip()
        current_file = cstr(self.get("export_file")).strip()
        if previous_file != current_file:
            frappe.throw(
                _("The generated regulatory workbook attachment cannot be changed from the Report Run form."),
                frappe.ValidationError,
            )

    def _validate_status_evidence(self):
        if self.status == "Sent" and (not self.sent_on or not cstr(self.sent_to).strip()):
            frappe.throw(
                _("Sent status requires the explicit send evidence (Sent To and Sent On)."),
                frappe.ValidationError,
            )

    def _validate_controlled_status_transition(self):
        if self.is_new():
            return
        previous = self.get_doc_before_save()
        if not previous or previous.status == self.status:
            return

        if self.status == "Sent" and not self.flags.get("vetedge_regulatory_send_action"):
            frappe.throw(
                _("Use the Regulatory Reporting send action to mark a report as Sent."),
                frappe.ValidationError,
            )
        if self.status in {"Accepted", "Rejected", "Superseded"} and not self.flags.get(
            "vetedge_regulatory_status_action"
        ):
            frappe.throw(
                _("Use the Regulatory Reporting status action to change submission status."),
                frappe.ValidationError,
            )

        try:
            assert_transition(
                cstr(previous.status).strip(),
                cstr(self.status).strip(),
                has_sent_evidence=bool(self.sent_on and cstr(self.sent_to).strip()),
            )
        except ValueError as exc:
            frappe.throw(_(str(exc)), frappe.ValidationError)
