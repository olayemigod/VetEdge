from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services.permissions import (
	get_assigned_branches,
	get_current_user,
	get_user_roles,
	user_has_global_branch_access,
)
from vetedge.services.report_visibility import (
	BRANCH_SCOPED_ROLES,
	normalize_dashboard_filters,
	validate_dashboard_access,
)

DASHBOARD_BRANCH_SEARCH_MAX_PAGE_LENGTH = 20


def _explicit_branch_scope(user: str | None) -> list[str]:
	"""Return assignments only when the existing dashboard policy makes them restrictive."""
	if user_has_global_branch_access(user) or not (get_user_roles(user) & BRANCH_SCOPED_ROLES):
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
	"""Return a small Branch search window using the established dashboard scope policy."""
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
	"""Validate a concrete Branch using the same normalization as existing dashboards."""
	branch = cstr(branch or "").strip()
	if not branch:
		return

	user = get_current_user()
	normalized = normalize_dashboard_filters(
		cstr(dashboard_key or "").strip(),
		{"branch": branch},
		user=user,
	)
	if cstr(normalized.get("branch") or "").strip() != branch or not frappe.db.exists("Branch", branch):
		frappe.throw(_("The selected Branch is not available to this user."), frappe.PermissionError)


@frappe.whitelist()
def get_executive_dashboard_payload(filters=None) -> dict:
	"""Validate Executive filters, then build one request-local optimized payload."""
	payload_filters = frappe.parse_json(filters) if isinstance(filters, str) else dict(filters or {})
	validate_dashboard_access("executive")
	validate_dashboard_branch_selection("executive", payload_filters.get("branch"))

	from vetedge.services.executive_dashboard_optimized import get_optimized_executive_dashboard_payload

	return get_optimized_executive_dashboard_payload(payload_filters)
