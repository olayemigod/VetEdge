from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

from vetedge.services import appointment_edgeui as base
from vetedge.services.branch_context import (
	get_active_veterinary_branch_context,
	validate_working_branch,
)
from vetedge.services.company_context import customer_is_allowed_for_company
from vetedge.services.company_context_compat import (
	get_patient_company_context,
	patient_is_available_for_company,
	repair_patient_company,
)


PATIENT_SEARCH_FIELDS = ("name", "patient_name", "primary_owner", "microchip_id")


def _parse_context(context: str | dict | None) -> dict[str, Any]:
	if not context:
		return {}
	if isinstance(context, dict):
		return dict(context)
	parsed = frappe.parse_json(context)
	return dict(parsed) if isinstance(parsed, dict) else {}


def _patient_option(row: dict, company: str) -> dict[str, Any]:
	context = get_patient_company_context(row)
	owner = context.get("primary_owner") or ""
	owner_label = base._owner_label(owner)
	return {
		"value": row.get("name"),
		"label": row.get("patient_name") or row.get("name"),
		"description": " · ".join(filter(None, [owner_label, row.get("species"), row.get("breed")])),
		"primary_owner": owner,
		"primary_owner_label": owner_label,
		"company": context.get("resolved_company") or company,
		"default_branch": row.get("default_branch"),
		"species": row.get("species"),
		"breed": row.get("breed"),
		"microchip_id": row.get("microchip_id"),
		"legacy_company_context": not bool(row.get("company")),
	}


def _search_patients(txt: str, company: str, start: int, page_length: int) -> list[dict[str, Any]]:
	if not frappe.has_permission("Veterinary Patient", "read"):
		return []

	filters: dict[str, Any] = {"status": ["!=", "Deceased"]}
	or_filters = None
	if txt:
		pattern = f"%{txt}%"
		or_filters = [["Veterinary Patient", fieldname, "like", pattern] for fieldname in PATIENT_SEARCH_FIELDS]

	# Existing patients may still have a blank Company because Branch was configured
	# after the one-time migration patch ran. Fetch permission-aware candidates, then
	# resolve blank Company from Default Branch without writing during search.
	fetch_length = min(max((start + page_length) * 10, 100), 500)
	rows = frappe.get_list(
		"Veterinary Patient",
		fields=[
			"name",
			"patient_name",
			"primary_owner",
			"company",
			"species",
			"breed",
			"microchip_id",
			"default_branch",
			"status",
		],
		filters=filters,
		or_filters=or_filters,
		order_by="patient_name asc, modified desc",
		start=0,
		page_length=fetch_length,
	)

	options: list[dict[str, Any]] = []
	for row in rows:
		if not patient_is_available_for_company(row, company):
			continue
		owner = row.get("primary_owner")
		if not owner or not customer_is_allowed_for_company(owner, company):
			continue
		options.append(_patient_option(row, company))

	return options[start : start + page_length]


@frappe.whitelist()
def get_appointment_form_bootstrap() -> dict[str, Any]:
	branch_context = get_active_veterinary_branch_context()
	current = branch_context.get("current_branch") or {}
	result = base.get_appointment_form_bootstrap()
	result.update(
		{
			"active_branch": current.get("name") or "",
			"default_branch": current.get("name") or "",
			"active_company": current.get("company") or branch_context.get("active_company") or "",
			"working_branch_label": current.get("branch_name") or "",
			"working_defaults": branch_context.get("active_defaults") or {},
			"requires_branch_selection": bool(branch_context.get("requires_branch_selection")),
			"can_switch_branch": bool(branch_context.get("can_switch_branch")),
		}
	)
	if not current.get("name") or not current.get("company"):
		result["can_create_appointment"] = False
		result["branch_error"] = _(
			"Select and configure a Veterinary working branch from Veterinary Home before creating an appointment."
		)
	return result


@frappe.whitelist()
def search_appointment_link(
	field: str,
	txt: str = "",
	context: str | dict | None = None,
	start: int = 0,
	page_length: int = 20,
) -> list[dict]:
	values = _parse_context(context)
	branch_context = get_active_veterinary_branch_context()
	current = branch_context.get("current_branch") or {}
	company = current.get("company") or branch_context.get("active_company") or ""
	start = max(cint(start), 0)
	page_length = min(max(cint(page_length) or 20, 1), 50)

	if field in {"patient", "owner"}:
		values["company"] = company
	if field == "patient":
		return _search_patients(str(txt or "").strip(), company, start, page_length)
	if field == "practitioner":
		values["branch"] = current.get("name") or values.get("branch")
	if field == "branch":
		return [
			{
				"value": row.get("name"),
				"label": row.get("branch_name") or row.get("name"),
				"description": row.get("company") or "",
				"company": row.get("company"),
			}
			for row in branch_context.get("configured_branches") or []
		]

	return base.search_appointment_link(
		field=field,
		txt=txt,
		context=values,
		start=start,
		page_length=page_length,
	)


@frappe.whitelist()
def get_patient_selection_context(patient: str) -> dict[str, Any]:
	branch_context = get_active_veterinary_branch_context()
	company = (branch_context.get("current_branch") or {}).get("company") or branch_context.get("active_company") or ""
	if not patient_is_available_for_company(patient, company):
		frappe.throw(
			_("The selected patient is not available for active Company {0}.").format(company),
			frappe.ValidationError,
		)
	resolved_company = repair_patient_company(patient, company)
	return base.get_patient_selection_context(patient, resolved_company)


@frappe.whitelist()
def create_edgeui_appointment(values: str | dict) -> dict[str, Any]:
	payload = base._parse_values(values)
	branch = validate_working_branch(payload.get("branch"), company=payload.get("company"))
	payload["branch"] = branch["name"]
	payload["company"] = branch["company"]
	if payload.get("patient"):
		repair_patient_company(payload["patient"], branch["company"])
	return base.create_edgeui_appointment(payload)
