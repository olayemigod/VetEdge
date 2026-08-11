from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services.permissions import (
	get_assigned_branches,
	get_current_user,
	user_has_global_branch_access,
)
from vetedge.services.report_visibility import validate_dashboard_access

DASHBOARD_BRANCH_SEARCH_MAX_PAGE_LENGTH = 20


def _explicit_branch_scope(user: str | None) -> list[str]:
	"""Return explicit Branch User Assignments, if the user is actually scoped by them.

	VetEdge's existing branch-access contract treats a non-elevated user with no
	Branch User Assignment rows as unrestricted by the assignment layer. The
	low-data search must preserve that behaviour rather than interpreting an empty
	assignment list as no access.
	"""
	if user_has_global_branch_access(user):
		return []
	return sorted(
		dict.fromkeys(
			cstr(branch).strip()
			for branch in get_assigned_branches(user)
			if cstr(branch).strip()
		)
	)


@frappe.whitelist()
def search_dashboard_branches(
	dashboard_key: str,
	txt: str = "",
	start: int = 0,
	page_length: int = 20,
) -> list[dict]:
	"""Return a small permission-aware Branch search window for dashboard filters."""
	user = get_current_user()
	key = cstr(dashboard_key or "").strip()
	validate_dashboard_access(key, user=user)

	if not frappe.has_permission("Branch", "read"):
		return []

	filters: list[list] = []
	explicit_scope = _explicit_branch_scope(user)
	if explicit_scope:
		filters.append(["Branch", "name", "in", explicit_scope])

	query = cstr(txt or "").strip()
	if query:
		filters.append(["Branch", "name", "like", f"%{query}%"])

	start = max(cint(start), 0)
	page_length = min(
		max(cint(page_length) or DASHBOARD_BRANCH_SEARCH_MAX_PAGE_LENGTH, 1),
		DASHBOARD_BRANCH_SEARCH_MAX_PAGE_LENGTH,
	)

	rows = frappe.get_list(
		"Branch",
		fields=["name"],
		filters=filters,
		order_by="name asc",
		start=start,
		page_length=page_length,
	)
	return [{"value": row.name, "label": row.name} for row in rows]


def validate_dashboard_branch_selection(dashboard_key: str, branch: str) -> None:
	"""Validate a concrete dashboard Branch selection without exposing extra records."""
	branch = cstr(branch or "").strip()
	if not branch:
		return

	user = get_current_user()
	validate_dashboard_access(cstr(dashboard_key or "").strip(), user=user)
	if not frappe.has_permission("Branch", "read"):
		frappe.throw(_("You are not permitted to read Branch records."), frappe.PermissionError)

	filters: list[list] = [["Branch", "name", "=", branch]]
	explicit_scope = _explicit_branch_scope(user)
	if explicit_scope:
		filters.append(["Branch", "name", "in", explicit_scope])

	rows = frappe.get_list("Branch", fields=["name"], filters=filters, page_length=1)
	if not rows:
		frappe.throw(_("The selected Branch is not available to this user."), frappe.PermissionError)


@frappe.whitelist()
def get_executive_dashboard_payload(filters=None) -> dict:
	"""Validate Executive Dashboard filters, then delegate to the existing reporting engine."""
	payload_filters = frappe.parse_json(filters) if isinstance(filters, str) else dict(filters or {})
	validate_dashboard_access("executive")
	validate_dashboard_branch_selection("executive", payload_filters.get("branch"))

	from vetedge.services.reporting_logic_v4 import get_dashboard_payload

	return get_dashboard_payload("executive", payload_filters)
