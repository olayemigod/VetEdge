from __future__ import annotations

import frappe
from frappe.utils import cint

from vetedge.install.custom_fields import (
	BRANCH_COST_CENTER_FIELD,
	BRANCH_DISPENSARY_WAREHOUSE_FIELD,
)

BRANCH_REFERENCE_FIELDS = (
	("Branch User Assignment", "branch"),
	("Branch Practitioner Assignment", "branch"),
	("Veterinary Patient", "default_branch"),
	("Veterinary Consultation", "service_branch"),
	("Veterinary Appointment", "branch"),
	("Veterinary Lab Order", "service_branch"),
	("Veterinary Vaccination Record", "service_branch"),
	("Veterinary Hospitalisation", "service_branch"),
	("Pet Grooming Appointment", "service_branch"),
	("Pet Grooming Session", "service_branch"),
	("Pet Boarding Booking", "service_branch"),
	("Pet Boarding Stay", "service_branch"),
	("Pet Boarding Care Record", "service_branch"),
	("Kennel", "branch"),
	("Veterinary Branch Registration Rule", "branch"),
)


def get_context_reconciliation_rows(branch_names: list[str] | None = None) -> list[dict]:
	"""
	Return VetEdge operational ERPNext Branches in the CoreEdge reconciliation shape.

	VetEdge does not own a separate Branch master. Discovery therefore uses only
	Branches already referenced by VetEdge configuration/workflows, unless an
	explicit branch list is supplied by an operator.
	"""
	names = _normalize_branch_names(branch_names)
	if names is None:
		names = _discover_vetedge_branch_names()
	if not names:
		return []

	branches = _get_branch_rows(names)
	return [_normalize_branch(row) for row in branches]


def _discover_vetedge_branch_names() -> list[str]:
	branches = set()
	for doctype, fieldname in BRANCH_REFERENCE_FIELDS:
		if not frappe.db.exists("DocType", doctype):
			continue
		meta = frappe.get_meta(doctype)
		if not meta.has_field(fieldname):
			continue
		for value in frappe.get_all(
			doctype,
			filters={fieldname: ["is", "set"]},
			pluck=fieldname,
			limit_page_length=0,
		):
			value = str(value or "").strip()
			if value:
				branches.add(value)
	return sorted(branches)


def _get_branch_rows(names: list[str]) -> list[dict]:
	meta = frappe.get_meta("Branch")
	fields = ["name"]
	for fieldname in (
		"branch",
		"branch_name",
		"branch_code",
		"disabled",
		"cost_center",
		BRANCH_COST_CENTER_FIELD,
		"warehouse",
		BRANCH_DISPENSARY_WAREHOUSE_FIELD,
	):
		if meta.has_field(fieldname) and fieldname not in fields:
			fields.append(fieldname)

	return frappe.get_all(
		"Branch",
		filters={"name": ["in", names]},
		fields=fields,
		limit_page_length=0,
		order_by="name asc",
	)


def _normalize_branch(row: dict) -> dict:
	company, sources, issue = _resolve_branch_company(row)
	label = (
		row.get("branch")
		or row.get("branch_name")
		or row.get("name")
		or ""
	)
	active = not bool(cint(row.get("disabled"))) if "disabled" in row else True

	return {
		"local_doctype": "Branch",
		"local_name": str(row.get("name") or "").strip(),
		"local_label": str(label).strip(),
		"local_code": str(row.get("branch_code") or "").strip(),
		"company": company,
		"active": active,
		"company_resolution_sources": sources,
		"normalization_issue": issue,
	}


def _resolve_branch_company(row: dict) -> tuple[str, list[str], str]:
	companies: dict[str, list[str]] = {}

	for fieldname in ("cost_center", BRANCH_COST_CENTER_FIELD):
		value = str(row.get(fieldname) or "").strip()
		if not value:
			continue
		company = str(frappe.db.get_value("Cost Center", value, "company") or "").strip()
		if company:
			companies.setdefault(company, []).append(fieldname)

	for fieldname in ("warehouse", BRANCH_DISPENSARY_WAREHOUSE_FIELD):
		value = str(row.get(fieldname) or "").strip()
		if not value:
			continue
		company = str(frappe.db.get_value("Warehouse", value, "company") or "").strip()
		if company:
			companies.setdefault(company, []).append(fieldname)

	if len(companies) == 1:
		company = next(iter(companies))
		return company, sorted(companies[company]), ""

	if len(companies) > 1:
		return (
			"",
			sorted({field for fields in companies.values() for field in fields}),
			"Branch cost-center and warehouse mappings resolve to different Companies.",
		)

	return (
		"",
		[],
		"Company could not be derived from the Branch cost-center or warehouse mapping; operator review is required.",
	)


def _normalize_branch_names(branch_names: list[str] | None) -> list[str] | None:
	if branch_names is None:
		return None
	return sorted({str(name or "").strip() for name in branch_names if str(name or "").strip()})
