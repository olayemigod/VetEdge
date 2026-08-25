from __future__ import annotations

import frappe
from frappe import _

from vetedge.services.appointment_flow import ensure_appointments_enabled
from vetedge.services.permissions import (
	get_assigned_branches,
	get_current_user,
	user_has_global_branch_access,
)
from vetedge.services.portal_access import require_internal_user

try:
	from edgesuite_ui.search_ranking import rank_search_records
except ImportError:  # Backward-compatible rollout before EdgeSuite fuzzy foundation is installed.
	rank_search_records = None

CANDIDATE_LIMIT = 100
RESULT_LIMIT = 20
MAX_ANCHORS = 4


def _require_front_desk_context() -> str:
	require_internal_user()
	ensure_appointments_enabled()
	return get_current_user() or frappe.session.user


def _legacy_link_options(fieldname: str, query: str) -> list[dict]:
	from vetedge.services.front_desk_action_center import get_front_desk_link_options

	return get_front_desk_link_options(fieldname=fieldname, query=query)


def _rank(options: list[dict], query: str, *, search_fields: tuple[str, ...]) -> list[dict]:
	if rank_search_records is None:
		return _legacy_filter(options, query)
	return list(
		rank_search_records(
			options,
			query,
			exact_fields=("value",),
			search_fields=search_fields,
			limit=RESULT_LIMIT,
		)
	)


def _legacy_filter(options: list[dict], query: str) -> list[dict]:
	term = str(query or "").strip().casefold()
	if not term:
		return options[:RESULT_LIMIT]
	matches = []
	for option in options:
		values = (option.get("value"), option.get("label"), option.get("description"))
		if any(term in str(value or "").casefold() for value in values):
			matches.append(option)
	return matches[:RESULT_LIMIT]


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


def _collect_rows(
	doctype: str,
	*,
	fields: list[str],
	filters: dict,
	search_fields: tuple[str, ...],
	query: str,
	order_by: str,
) -> list[dict]:
	text = str(query or "").strip()
	if not text:
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

	rows: list[dict] = []
	seen: set[str] = set()
	exact = frappe.get_list(
		doctype,
		fields=fields,
		filters=filters,
		or_filters={fieldname: text for fieldname in search_fields},
		order_by=order_by,
		page_length=CANDIDATE_LIMIT,
	)
	for source in exact:
		row = dict(source)
		key = str(row.get("name") or "")
		if key and key not in seen:
			seen.add(key)
			rows.append(row)

	for anchor in _query_anchors(text):
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


def _branch_options(query: str) -> list[dict]:
	filters = {}
	user = get_current_user()
	assigned = get_assigned_branches(user)
	if assigned and not user_has_global_branch_access(user):
		filters["name"] = ["in", assigned]
	rows = _collect_rows(
		"Branch",
		fields=["name"],
		filters=filters,
		search_fields=("name",),
		query=query,
		order_by="name asc",
	)
	options = [{"value": row.get("name"), "label": row.get("name")} for row in rows]
	return _rank(options, query, search_fields=("label",))


def _practitioner_options(query: str) -> list[dict]:
	users = frappe.get_all(
		"Has Role",
		filters={"role": "VetEdge Doctor", "parenttype": "User"},
		pluck="parent",
	)
	if not users:
		return []
	rows = _collect_rows(
		"User",
		fields=["name", "full_name"],
		filters={"name": ["in", users], "enabled": 1},
		search_fields=("name", "full_name"),
		query=query,
		order_by="full_name asc",
	)
	options = [
		{
			"value": row.get("name"),
			"label": row.get("full_name") or row.get("name"),
			"description": row.get("name") if row.get("full_name") and row.get("full_name") != row.get("name") else "",
		}
		for row in rows
	]
	return _rank(options, query, search_fields=("label", "description"))


@frappe.whitelist()
def get_front_desk_link_options(fieldname: str, query: str = "") -> list[dict]:
	"""Bounded fuzzy-aware provider for existing Front Desk EdgeLinkField controls."""
	_require_front_desk_context()
	text = str(query or "").strip()
	if rank_search_records is None:
		return _legacy_link_options(fieldname, text)
	if fieldname == "branch":
		return _branch_options(text)
	if fieldname == "practitioner":
		return _practitioner_options(text)
	frappe.throw(_("Unsupported Front Desk Link field."), frappe.ValidationError)
