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
MAX_ANCHORS = 4


def _legacy_link_options(resource: str, fieldname: str, query: str, page_length: int) -> list[dict[str, Any]]:
	from vetedge.services.master_workspace import get_master_link_options

	return get_master_link_options(
		resource=resource,
		fieldname=fieldname,
		query=query,
		page_length=page_length,
	)


def _query_anchors(query: str) -> tuple[str, ...]:
	term = " ".join(str(query or "").strip().casefold().split())
	if not term:
		return ()
	anchors = [term]
	for token in term.split():
		if len(token) >= 3:
			anchors.append(token[:3])
		if len(token) >= 2:
			anchors.append(token[-2:])
	unique: list[str] = []
	for anchor in anchors:
		if anchor and anchor not in unique:
			unique.append(anchor)
		if len(unique) >= MAX_ANCHORS:
			break
	return tuple(unique)


def _candidate_rows(
	doctype: str,
	*,
	fields: list[str],
	filters: dict[str, Any],
	search_fields: list[str],
	query: str,
	order_by: str,
) -> list[dict[str, Any]]:
	search_text = str(query or "").strip()
	if not search_text:
		return [
			dict(row)
			for row in frappe.get_list(
				doctype,
				fields=fields,
				filters=filters,
				order_by=order_by,
				page_length=CANDIDATE_LIMIT,
			)
		]

	rows: list[dict[str, Any]] = []
	seen: set[str] = set()
	exact = frappe.get_list(
		doctype,
		fields=fields,
		filters=filters,
		or_filters={fieldname: search_text for fieldname in search_fields},
		order_by=order_by,
		page_length=CANDIDATE_LIMIT,
	)
	for source in exact:
		row = dict(source)
		name = str(row.get("name") or "")
		if name and name not in seen:
			seen.add(name)
			rows.append(row)

	for anchor in _query_anchors(search_text):
		remaining = CANDIDATE_LIMIT - len(rows)
		if remaining <= 0:
			break
		matches = frappe.get_list(
			doctype,
			fields=fields,
			filters=filters,
			or_filters={fieldname: ["like", f"%{anchor}%"] for fieldname in search_fields},
			order_by=order_by,
			page_length=remaining,
		)
		for source in matches:
			row = dict(source)
			name = str(row.get("name") or "")
			if not name or name in seen:
				continue
			seen.add(name)
			rows.append(row)
			if len(rows) >= CANDIDATE_LIMIT:
				break
	return rows


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
	rows = _candidate_rows(
		options,
		fields=fields,
		filters=filters,
		search_fields=search_fields,
		query=query,
		order_by=f"{title_field} asc",
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
