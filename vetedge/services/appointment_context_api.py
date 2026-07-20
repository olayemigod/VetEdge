from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from vetedge.services import appointment_edgeui as base
from vetedge.services.branch_context import (
	get_active_veterinary_branch_context,
	validate_working_branch,
)


def _parse_context(context: str | dict | None) -> dict[str, Any]:
	if not context:
		return {}
	if isinstance(context, dict):
		return dict(context)
	parsed = frappe.parse_json(context)
	return dict(parsed) if isinstance(parsed, dict) else {}


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
	company = current.get("company") or branch_context.get("active_company")

	if field in {"patient", "owner"}:
		values["company"] = company
	if field == "patient":
		# Company is the patient-isolation boundary. A patient may attend another
		# permitted branch, so the working branch must not hide that patient.
		values.pop("branch", None)
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
def create_edgeui_appointment(values: str | dict) -> dict[str, Any]:
	payload = base._parse_values(values)
	branch = validate_working_branch(payload.get("branch"), company=payload.get("company"))
	payload["branch"] = branch["name"]
	payload["company"] = branch["company"]
	return base.create_edgeui_appointment(payload)
