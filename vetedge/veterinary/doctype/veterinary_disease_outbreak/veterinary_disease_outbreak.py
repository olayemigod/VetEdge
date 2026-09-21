from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, getdate

from vetedge.install.custom_fields import BRANCH_NADIS_ADMIN_LEVEL_1_FIELD
from vetedge.services.permissions import get_assigned_branches, get_current_user, user_has_global_branch_access


COUNT_FIELDS = (
    "number_susceptible",
    "number_cases",
    "number_deaths",
    "number_slaughtered",
    "number_destroyed",
    "number_vaccinated_around_outbreak",
)


class VeterinaryDiseaseOutbreak(Document):
    def before_validate(self):
        self.country = "Nigeria"
        self._derive_branch_context()
        self._derive_disease_mapping()
        self._derive_animal_species_mappings()

    def validate(self):
        self._validate_branch_access()
        self._validate_follow_up()
        self._validate_counts()
        self._validate_timeline()

    def _validate_branch_access(self):
        user = get_current_user()
        if user_has_global_branch_access(user):
            return
        allowed = {
            cstr(branch).strip()
            for branch in get_assigned_branches(user)
            if cstr(branch).strip()
        }
        if not allowed:
            frappe.throw(_("You do not have an assigned Veterinary Branch for disease-outbreak reporting."), frappe.PermissionError)
        if cstr(self.service_branch).strip() not in allowed:
            frappe.throw(_("You do not have access to the selected Reporting Branch."), frappe.PermissionError)

    def _derive_branch_context(self):
        if not self.service_branch:
            return
        branch = frappe.get_doc("Branch", self.service_branch)
        branch.check_permission("read")
        meta = frappe.get_meta("Branch")
        branch_company = cstr(branch.get("company") if meta.has_field("company") else "").strip()
        selected_company = cstr(self.company).strip()
        if branch_company and selected_company and branch_company != selected_company:
            frappe.throw(
                _("Reporting Branch {0} belongs to Company {1}, not {2}.").format(
                    self.service_branch,
                    branch_company,
                    selected_company,
                ),
                frappe.ValidationError,
            )
        if branch_company:
            self.company = branch_company
        if meta.has_field(BRANCH_NADIS_ADMIN_LEVEL_1_FIELD):
            self.admin_level_1 = branch.get(BRANCH_NADIS_ADMIN_LEVEL_1_FIELD)

    def _derive_disease_mapping(self):
        if not self.disease:
            self.nadis_disease = None
            return
        diagnosis = frappe.get_doc("Veterinary Diagnosis", self.disease)
        diagnosis.check_permission("read")
        if cint(diagnosis.get("disabled")):
            frappe.throw(_("Disabled Veterinary Diagnosis {0} cannot be used for an outbreak.").format(self.disease), frappe.ValidationError)
        self.nadis_disease = diagnosis.get("nadis_disease")

    def _derive_animal_species_mappings(self):
        cache: dict[str, str | None] = {}
        for row in self.get("animals_affected") or []:
            if not row.species:
                row.nadis_species = None
                continue
            if row.species not in cache:
                species = frappe.get_doc("Veterinary Species", row.species)
                species.check_permission("read")
                if cint(species.get("disabled")):
                    frappe.throw(_("Disabled Veterinary Species {0} cannot be used for an outbreak.").format(row.species), frappe.ValidationError)
                cache[row.species] = species.get("nadis_species")
            row.nadis_species = cache[row.species]

    def _validate_follow_up(self):
        if self.outbreak_type == "Follow up outbreak" and not self.parent_outbreak:
            frappe.throw(_("Original Outbreak is required for a follow-up outbreak."), frappe.ValidationError)
        if self.parent_outbreak and self.name and self.parent_outbreak == self.name:
            frappe.throw(_("An outbreak cannot reference itself as the Original Outbreak."), frappe.ValidationError)
        if not self.parent_outbreak:
            return

        if not frappe.db.exists("Veterinary Disease Outbreak", self.parent_outbreak):
            frappe.throw(_("Original Outbreak {0} does not exist.").format(self.parent_outbreak), frappe.ValidationError)

        original = frappe.get_doc("Veterinary Disease Outbreak", self.parent_outbreak)
        original.check_permission("read")

        if self.disease and original.disease and self.disease != original.disease:
            frappe.throw(
                _("A follow-up outbreak must use the same Disease as the Original Outbreak."),
                frappe.ValidationError,
            )

        current_company = cstr(self.company).strip()
        original_company = cstr(original.company).strip()
        if current_company and original_company and current_company != original_company:
            frappe.throw(
                _("A follow-up outbreak must belong to the same Company as the Original Outbreak."),
                frappe.ValidationError,
            )

        current_branch = cstr(self.service_branch).strip()
        original_branch = cstr(original.service_branch).strip()
        if current_branch and original_branch and current_branch != original_branch:
            frappe.throw(
                _("A follow-up outbreak must use the same Reporting Branch as the Original Outbreak."),
                frappe.ValidationError,
            )

    def _validate_counts(self):
        for fieldname in ("number_new_outbreaks", "total_outbreaks"):
            if cint(self.get(fieldname)) < 0:
                frappe.throw(_("{0} cannot be negative.").format(self.meta.get_label(fieldname)), frappe.ValidationError)
        for row in self.get("animals_affected") or []:
            for fieldname in COUNT_FIELDS:
                if cint(row.get(fieldname)) < 0:
                    frappe.throw(
                        _("{0} cannot be negative in Animals Affected row {1}.").format(row.meta.get_label(fieldname), row.idx),
                        frappe.ValidationError,
                    )
            cases = cint(row.get("number_cases"))
            deaths = cint(row.get("number_deaths"))
            if cases and deaths > cases:
                frappe.throw(
                    _("Deaths cannot exceed Cases in Animals Affected row {0}.").format(row.idx),
                    frappe.ValidationError,
                )

    def _validate_timeline(self):
        ordered = [
            ("date_outbreak_started", self.date_outbreak_started),
            ("date_reported_to_vet", self.date_reported_to_vet),
            ("date_investigated", self.date_investigated),
            ("date_final_diagnosis", self.date_final_diagnosis),
        ]
        previous = None
        previous_label = None
        for fieldname, value in ordered:
            if not value:
                continue
            current = getdate(value)
            if previous and current < previous:
                frappe.throw(
                    _("{0} cannot be earlier than {1}.").format(self.meta.get_label(fieldname), previous_label),
                    frappe.ValidationError,
                )
            previous = current
            previous_label = self.meta.get_label(fieldname)
