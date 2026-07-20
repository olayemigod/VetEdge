from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cstr

from vetedge.services.permissions import (
	ELEVATED_ROLES,
	get_assigned_branches,
	get_user_roles,
	is_internal_staff_user,
	user_has_global_branch_access,
)


def _clean(value: Any) -> str:
	return cstr(value or "").strip()


def get_single_site_company() -> str:
	if not frappe.db.exists("DocType", "Company"):
		return ""
	companies = frappe.get_all("Company", pluck="name", limit_page_length=2)
	return _clean(companies[0]) if len(companies) == 1 else ""


def get_branch_company(branch: str | None) -> str:
	branch = _clean(branch)
	if not branch or not frappe.db.exists("DocType", "Branch") or not frappe.db.exists("Branch", branch):
		return ""
	meta = frappe.get_meta("Branch")
	if meta.has_field("vetedge_company"):
		company = _clean(frappe.db.get_value("Branch", branch, "vetedge_company"))
		if company:
			return company
	return get_single_site_company()


def get_patient_company_context(patient: str | dict | Any) -> dict[str, str]:
	if isinstance(patient, str):
		values = frappe.db.get_value(
			"Veterinary Patient",
			patient,
			["name", "company", "default_branch", "primary_owner", "status"],
			as_dict=True,
		) or frappe._dict()
	else:
		values = frappe._dict(patient or {})

	name = _clean(values.get("name"))
	explicit_company = _clean(values.get("company"))
	branch = _clean(values.get("default_branch"))
	branch_company = get_branch_company(branch)
	resolved_company = explicit_company or branch_company or get_single_site_company()
	return {
		"patient": name,
		"company": explicit_company,
		"default_branch": branch,
		"branch_company": branch_company,
		"resolved_company": resolved_company,
		"primary_owner": _clean(values.get("primary_owner")),
		"status": _clean(values.get("status")),
	}


def patient_is_available_for_company(patient: str | dict | Any, company: str | None) -> bool:
	company = _clean(company)
	if not company:
		return False
	context = get_patient_company_context(patient)
	return bool(context.get("resolved_company") == company and context.get("status") != "Deceased")


def repair_patient_company(patient: str, company: str | None = None) -> str:
	patient = _clean(patient)
	if not patient or not frappe.db.exists("Veterinary Patient", patient):
		frappe.throw(_("Select a valid Veterinary Patient."), frappe.ValidationError)

	context = get_patient_company_context(patient)
	requested_company = _clean(company)
	explicit_company = context.get("company") or ""
	resolved_company = context.get("resolved_company") or ""

	if explicit_company:
		if requested_company and explicit_company != requested_company:
			frappe.throw(
				_("The selected patient belongs to Company {0}, not active Company {1}.").format(
					explicit_company,
					requested_company,
				),
				frappe.ValidationError,
			)
		return explicit_company

	if not resolved_company:
		frappe.throw(
			_("The selected patient has no unambiguous Company. Configure the patient's Default Branch or Company."),
			frappe.ValidationError,
		)
	if requested_company and resolved_company != requested_company:
		frappe.throw(
			_("The selected patient's branch resolves to Company {0}, not active Company {1}.").format(
				resolved_company,
				requested_company,
			),
			frappe.ValidationError,
		)

	frappe.db.set_value(
		"Veterinary Patient",
		patient,
		"company",
		resolved_company,
		update_modified=False,
	)
	return resolved_company


def repair_resolvable_company_context(branch: str | None = None) -> dict[str, int]:
	branch = _clean(branch)
	conditions = ["IFNULL(company, '') = ''"]
	params: dict[str, str] = {}
	if branch:
		conditions.append("default_branch = %(branch)s")
		params["branch"] = branch

	patients = frappe.db.sql(
		f"""
		SELECT name, company, default_branch, primary_owner, status
		FROM `tabVeterinary Patient`
		WHERE {' AND '.join(conditions)}
		""",
		params,
		as_dict=True,
	)
	patient_updates = 0
	for patient in patients:
		resolved_company = get_patient_company_context(patient).get("resolved_company") or ""
		if not resolved_company:
			continue
		frappe.db.set_value(
			"Veterinary Patient",
			patient.name,
			"company",
			resolved_company,
			update_modified=False,
		)
		patient_updates += 1

	appointment_updates = 0
	if frappe.db.exists("DocType", "Veterinary Appointment") and frappe.get_meta(
		"Veterinary Appointment"
	).has_field("company"):
		before = frappe.db.sql(
			"""
			SELECT COUNT(*)
			FROM `tabVeterinary Appointment` a
			INNER JOIN `tabVeterinary Patient` p ON p.name = a.patient
			WHERE IFNULL(a.company, '') = ''
				AND IFNULL(a.docstatus, 0) = 0
				AND IFNULL(p.company, '') != ''
			"""
		)[0][0]
		frappe.db.sql(
			"""
			UPDATE `tabVeterinary Appointment` a
			INNER JOIN `tabVeterinary Patient` p ON p.name = a.patient
			SET a.company = p.company
			WHERE IFNULL(a.company, '') = ''
				AND IFNULL(a.docstatus, 0) = 0
				AND IFNULL(p.company, '') != ''
			"""
		)
		appointment_updates = int(before or 0)

	return {
		"patients_updated": patient_updates,
		"draft_appointments_updated": appointment_updates,
	}


def sync_branch_company_context(doc, method: str | None = None) -> None:
	if getattr(doc, "doctype", None) != "Branch":
		return
	if not _clean(getattr(doc, "vetedge_company", None)):
		return
	repair_resolvable_company_context(branch=getattr(doc, "name", None))


def validate_patient_history_access(patient: str, user: str | None = None) -> None:
	user = user or getattr(frappe.session, "user", None)
	if not user or user == "Guest" or not is_internal_staff_user(user):
		frappe.throw(_("This action is only available to Veterinary staff."), frappe.PermissionError)
	if not frappe.db.exists("Veterinary Patient", patient):
		frappe.throw(_("Select a valid Veterinary Patient."), frappe.ValidationError)
	if not frappe.has_permission("Veterinary Patient", "read", doc=patient, user=user):
		frappe.throw(_("You are not permitted to read this Veterinary Patient."), frappe.PermissionError)

	if user_has_global_branch_access(user) or get_user_roles(user).intersection(ELEVATED_ROLES):
		return

	context = get_patient_company_context(patient)
	assigned_branches = get_assigned_branches(user)
	patient_branch = context.get("default_branch") or ""
	if assigned_branches and patient_branch and patient_branch not in assigned_branches:
		frappe.throw(
			_("You are not assigned to the patient's Default Branch {0}.").format(patient_branch),
			frappe.PermissionError,
		)

	try:
		from vetedge.services.branch_context import get_working_company

		working_company = _clean(get_working_company(user=user))
	except (ImportError, ModuleNotFoundError, RuntimeError):
		working_company = ""
	resolved_company = context.get("resolved_company") or ""
	if working_company and resolved_company and working_company != resolved_company:
		frappe.throw(
			_("Switch to Company {0} before viewing this patient's medical history.").format(resolved_company),
			frappe.PermissionError,
		)


@frappe.whitelist()
def get_company_context_audit() -> dict[str, Any]:
	user = getattr(frappe.session, "user", None)
	if not user or not get_user_roles(user).intersection(ELEVATED_ROLES):
		frappe.throw(_("Veterinary administrator access is required."), frappe.PermissionError)

	patient_counts = frappe.db.sql(
		"""
		SELECT
			COUNT(*) AS total,
			SUM(CASE WHEN IFNULL(company, '') = '' THEN 1 ELSE 0 END) AS missing_company
		FROM `tabVeterinary Patient`
		""",
		as_dict=True,
	)[0]
	resolvable = 0
	ambiguous = 0
	for patient in frappe.db.sql(
		"""
		SELECT name, company, default_branch, primary_owner, status
		FROM `tabVeterinary Patient`
		WHERE IFNULL(company, '') = ''
		""",
		as_dict=True,
	):
		if get_patient_company_context(patient).get("resolved_company"):
			resolvable += 1
		else:
			ambiguous += 1

	appointment_missing = 0
	if frappe.db.exists("DocType", "Veterinary Appointment") and frappe.get_meta(
		"Veterinary Appointment"
	).has_field("company"):
		appointment_missing = int(
			frappe.db.sql(
				"SELECT COUNT(*) FROM `tabVeterinary Appointment` WHERE IFNULL(company, '') = ''"
			)[0][0]
			or 0
		)

	return {
		"patients": {
			"total": int(patient_counts.get("total") or 0),
			"missing_company": int(patient_counts.get("missing_company") or 0),
			"resolvable_from_branch_or_single_company": resolvable,
			"ambiguous": ambiguous,
		},
		"appointments": {"missing_company": appointment_missing},
		"historical_records": {
			"company_filter_applied": False,
			"note": _(
				"Consultations, vitals, laboratory and vaccination history remain patient-linked and are not hidden by a Company filter."
			),
		},
		"repair_command": "bench --site <site> execute vetedge.services.company_context_compat.repair_resolvable_company_context",
	}
