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


def _branch_options(query: str) -> list[dict]:
	filters = {}
	user = get_current_user()
	assigned = get_assigned_branches(user)
	if assigned and not user_has_global_branch_access(user):
		filters["name"] = ["in", assigned]
	rows = frappe.get_list(
		"Branch",
		fields=["name"],
		filters=filters,
		order_by="name asc",
		page_length=CANDIDATE_LIMIT,
	)
	options = [{"value": row.name, "label": row.name} for row in rows]
	return _rank(options, query, search_fields=("label",))


def _practitioner_options(query: str) -> list[dict]:
	users = frappe.get_all(
		"Has Role",
		filters={"role": "VetEdge Doctor", "parenttype": "User"},
		pluck="parent",
	)
	if not users:
		return []
	rows = frappe.get_list(
		"User",
		fields=["name", "full_name"],
		filters={"name": ["in", users], "enabled": 1},
		order_by="full_name asc",
		page_length=CANDIDATE_LIMIT,
	)
	options = [
		{
			"value": row.name,
			"label": row.full_name or row.name,
			"description": row.name if row.full_name and row.full_name != row.name else "",
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
