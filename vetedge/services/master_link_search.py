from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

from vetedge.services.master_workspace import _require_master

try:
	from edgesuite_ui.search_ranking import rank_search_records
except ImportError:  # Backward-compatible rollout before EdgeSuite fuzzy foundation is installed.
	rank_search_records = None

CANDIDATE_LIMIT = 100
RESULT_LIMIT_MAX = 50


def _legacy_link_options(resource: str, fieldname: str, query: str, page_length: int) -> list[dict[str, Any]]:
	from vetedge.services.master_workspace import get_master_link_options

	return get_master_link_options(
		resource=resource,
		fieldname=fieldname,
		query=query,
		page_length=page_length,
	)


@frappe.whitelist()
def get_master_link_options(
	resource: str,
	fieldname: str,
	query: str = "",
	page_length: int = 20,
) -> list[dict[str, Any]]:
	"""Fuzzy-aware bounded Link provider for the existing VetEdge Master Workspace."""
	if rank_search_records is None:
		return _legacy_link_options(resource, fieldname, query, page_length)

	config = _require_master(resource)
	meta = frappe.get_meta(config["doctype"])
	field = meta.get_field(fieldname)
	if not field or field.fieldtype != "Link":
		frappe.throw(_("This field does not support record lookup."), frappe.ValidationError)

	options = field.options
	if not options or not frappe.db.exists("DocType", options) or not frappe.has_permission(options, "read"):
		return []

	filters = dict((config.get("link_filters") or {}).get(fieldname) or {})
	option_meta = frappe.get_meta(options)
	title_field = (
		option_meta.title_field
		if option_meta.title_field and option_meta.has_field(option_meta.title_field)
		else "name"
	)
	search_fields = ["name"]
	for candidate in (title_field, *(str(option_meta.search_fields or "").split(","))):
		candidate = str(candidate or "").strip()
		if candidate and option_meta.has_field(candidate) and candidate not in search_fields:
			search_fields.append(candidate)
	search_fields = search_fields[:5]

	fields = list(search_fields)
	if title_field not in fields:
		fields.append(title_field)
	rows = frappe.get_list(
		options,
		fields=fields,
		filters=filters,
		order_by=f"{title_field} asc",
		page_length=CANDIDATE_LIMIT,
	)
	candidates = []
	for row in rows:
		name = row.get("name")
		label = row.get(title_field) or name
		aliases = [
			row.get(search_field)
			for search_field in search_fields
			if search_field not in {"name", title_field} and row.get(search_field)
		]
		candidates.append(
			{
				"value": name,
				"label": label,
				"description": name if title_field != "name" else "",
				"aliases": aliases,
			}
		)

	result_limit = min(max(cint(page_length) or 20, 1), RESULT_LIMIT_MAX)
	ranked = rank_search_records(
		candidates,
		str(query or "").strip(),
		exact_fields=("value",),
		search_fields=("label", "description"),
		alias_fields=("aliases",),
		limit=result_limit,
	)
	return [
		{
			"value": row.get("value"),
			"label": row.get("label"),
			"description": row.get("description") or "",
		}
		for row in ranked
	]
