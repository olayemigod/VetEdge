from __future__ import annotations

from typing import Any, Callable

import frappe
from frappe import _
from frappe.utils import cint

from vetedge.services import clinical_workspace, pricing_master_workspace

CANDIDATE_LIMIT = 100


def _shared_ranker() -> Callable[..., list] | None:
	try:
		from edgesuite_ui.search_ranking import rank_search_records
	except (ImportError, ModuleNotFoundError):
		return None
	return rank_search_records


def _rank(rows: list[dict[str, Any]], query: str, limit: int) -> list[dict[str, Any]]:
	ranker = _shared_ranker()
	if ranker is None:
		return rows[:limit]
	return list(
		ranker(
			rows,
			query or "",
			exact_fields=("value",),
			search_fields=("label", "description"),
			limit=limit,
		)
	)


@frappe.whitelist()
def get_clinical_link_options(
	kind: str,
	search: str = "",
	branch: str | None = None,
	limit: int = 20,
) -> list[dict[str, Any]]:
	if _shared_ranker() is None:
		return clinical_workspace.get_clinical_link_options(kind, search, branch, limit)

	clinical_workspace._require_clinical_context()
	clinical_workspace._validate_branch(branch)
	page_len = min(max(cint(limit) or 20, 1), 50)

	if kind == "practitioner":
		rows = clinical_workspace.get_veterinary_doctor_users(
			"User", "", "name", 0, CANDIDATE_LIMIT, {}
		)
		options = [{"value": row[0], "label": row[1]} for row in rows]
		return _rank(options, search, page_len)
	if kind == "treatment_item":
		rows = clinical_workspace.get_treatment_item_link_options(
			"Item", "", "name", 0, CANDIDATE_LIMIT, {}
		)
		options = [{"value": row[0], "label": row[1]} for row in rows]
		return _rank(options, search, page_len)

	return clinical_workspace.get_clinical_link_options(kind, search, branch, limit)


@frappe.whitelist()
def get_pricing_master_link_options(
	resource: str,
	fieldname: str,
	query: str = "",
	page_length: int = 20,
) -> list[dict[str, Any]]:
	if _shared_ranker() is None:
		return pricing_master_workspace.get_pricing_master_link_options(
			resource, fieldname, query, page_length
		)

	config = pricing_master_workspace._require_resource(resource)
	meta = frappe.get_meta(config["doctype"])
	field = meta.get_field(fieldname)
	if not field or field.fieldtype != "Link":
		frappe.throw(_("This field does not support record lookup."), frappe.ValidationError)

	options = field.options
	if (
		not options
		or not frappe.db.exists("DocType", options)
		or not frappe.has_permission(options, "read")
	):
		return []

	option_meta = frappe.get_meta(options)
	filters = {
		key: value
		for key, value in dict(
			(config.get("link_filters") or {}).get(fieldname) or {}
		).items()
		if option_meta.has_field(key)
	}
	title_field = (
		option_meta.title_field
		if option_meta.title_field and option_meta.has_field(option_meta.title_field)
		else "name"
	)
	fields = ["name"]
	if title_field != "name":
		fields.append(title_field)
	for candidate in str(option_meta.search_fields or "").split(","):
		candidate = candidate.strip()
		if candidate and option_meta.has_field(candidate) and candidate not in fields:
			fields.append(candidate)
		if len(fields) >= 6:
			break

	rows = frappe.get_list(
		options,
		fields=fields,
		filters=filters,
		order_by=f"{title_field} asc",
		page_length=CANDIDATE_LIMIT,
	)
	search_fields = [fieldname for fieldname in fields if fieldname != "name"]
	candidates = []
	for row in rows:
		description_parts = [str(row.get(name) or "") for name in search_fields]
		candidates.append(
			{
				"value": row.get("name"),
				"label": row.get(title_field) or row.get("name"),
				"description": " · ".join(
					part for part in description_parts if part and part != row.get(title_field)
				),
			}
		)
	limit = min(max(cint(page_length) or 20, 1), 50)
	return _rank(candidates, query, limit)
