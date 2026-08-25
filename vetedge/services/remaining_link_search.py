from __future__ import annotations

from collections.abc import Callable
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

from vetedge.services import clinical_workspace, pricing_master_workspace

CANDIDATE_LIMIT = 100
MAX_ANCHORS = 4


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


def _query_anchors(query: str) -> tuple[str, ...]:
	term = " ".join(str(query or "").strip().casefold().split())
	if not term:
		return ("",)
	anchors = [term]
	for token in term.split():
		if len(token) >= 3:
			anchors.append(token[:3])
		if len(token) >= 2:
			anchors.append(token[-2:])
	unique: list[str] = []
	for anchor in anchors:
		if anchor not in unique:
			unique.append(anchor)
		if len(unique) >= MAX_ANCHORS:
			break
	return tuple(unique)


def _collect_tuple_candidates(searcher: Callable[[str, int], list], query: str) -> list[list[Any]]:
	rows: list[list[Any]] = []
	seen: set[str] = set()
	for anchor in _query_anchors(query):
		remaining = CANDIDATE_LIMIT - len(rows)
		if remaining <= 0:
			break
		for row in searcher(anchor, remaining):
			key = str(row[0] if row else "")
			if not key or key in seen:
				continue
			seen.add(key)
			rows.append(row)
			if len(rows) >= CANDIDATE_LIMIT:
				break
	return rows


def _pricing_rows(
	doctype: str,
	*,
	fields: list[str],
	filters: dict[str, Any],
	search_fields: tuple[str, ...],
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
		key = str(row.get("name") or "")
		if key and key not in seen:
			seen.add(key)
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
			key = str(row.get("name") or "")
			if not key or key in seen:
				continue
			seen.add(key)
			rows.append(row)
			if len(rows) >= CANDIDATE_LIMIT:
				break
	return rows


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
		rows = _collect_tuple_candidates(
			lambda txt, page_length: clinical_workspace.get_veterinary_doctor_users(
				"User", txt, "name", 0, page_length, {}
			),
			search,
		)
		options = [{"value": row[0], "label": row[1]} for row in rows]
		return _rank(options, search, page_len)
	if kind == "treatment_item":
		rows = _collect_tuple_candidates(
			lambda txt, page_length: clinical_workspace.get_treatment_item_link_options(
				"Item", txt, "name", 0, page_length, {}
			),
			search,
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

	search_fields = tuple(dict.fromkeys(fields))
	rows = _pricing_rows(
		options,
		fields=fields,
		filters=filters,
		search_fields=search_fields,
		query=query,
		order_by=f"{title_field} asc",
	)
	description_fields = [name for name in fields if name not in {"name", title_field}]
	candidates = []
	for row in rows:
		description_parts = [str(row.get(name) or "") for name in description_fields]
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
