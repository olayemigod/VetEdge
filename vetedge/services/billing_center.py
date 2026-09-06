from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, getdate

from vetedge.services.permissions import (
	ACCOUNTS_COLLECTION_ROLES,
	ELEVATED_ROLES,
	FRONT_DESK_ROLES,
	ROLE_BRANCH_MANAGER,
	get_assigned_branches,
	get_current_user,
	user_has_any_role,
	user_has_global_branch_access,
)
from vetedge.services.portal_access import require_internal_user

BILLING_SESSION_DOCTYPE = "Veterinary Billing Session"
PATIENT_DOCTYPE = "Veterinary Patient"
PAGE_LENGTH_DEFAULT = 25
PAGE_LENGTH_MAX = 100
PATIENT_SEARCH_CANDIDATE_LIMIT = 50
DEFAULT_ACTIVITY_FILTER = "actionable"
ALLOWED_ACTIVITY_FILTERS = {"actionable", "all", "empty"}
BILLING_CENTER_ROLES = {
	*ELEVATED_ROLES,
	*FRONT_DESK_ROLES,
	*ACCOUNTS_COLLECTION_ROLES,
	ROLE_BRANCH_MANAGER,
	"VetEdge Branch Manager",
}
OPEN_SESSION_STATUSES = ("Draft", "Active", "Partially Paid")
ALLOWED_SESSION_STATUSES = {"Draft", "Active", "Partially Paid", "Paid", "Closed", "Cancelled"}
LINK_FIELDS = {"company", "branch", "customer", "animal"}


def _parse_filters(filters: str | dict | None) -> dict[str, Any]:
	if not filters:
		return {}
	if isinstance(filters, dict):
		return dict(filters)
	parsed = frappe.parse_json(filters)
	if not isinstance(parsed, dict):
		frappe.throw(_("Billing Center filters must be a JSON object."), frappe.ValidationError)
	return dict(parsed)


def _require_billing_center_access() -> str:
	require_internal_user()
	user = get_current_user() or frappe.session.user
	if not user_has_any_role(user, BILLING_CENTER_ROLES):
		frappe.throw(_("You are not permitted to use Billing Center."), frappe.PermissionError)
	if not frappe.has_permission(BILLING_SESSION_DOCTYPE, "read"):
		frappe.throw(_("You are not permitted to view billing sessions."), frappe.PermissionError)
	return user


def _page_values(start: int, page_length: int) -> tuple[int, int]:
	return max(cint(start), 0), min(max(cint(page_length) or PAGE_LENGTH_DEFAULT, 1), PAGE_LENGTH_MAX)


def _branch_scope(user: str, requested_branch: str | None) -> tuple[list[str] | None, bool]:
	branch = cstr(requested_branch or "").strip()
	if user_has_global_branch_access(user):
		return ([branch] if branch else None), False

	assigned = sorted({cstr(value).strip() for value in get_assigned_branches(user) if cstr(value).strip()})
	if branch:
		if branch not in assigned:
			frappe.throw(_("You are not assigned to Branch {0}.").format(branch), frappe.PermissionError)
		return [branch], True

	# Billing is financially sensitive. Unlike older compatibility reads, an
	# operational user with no branch assignment must never become company-wide.
	return assigned, True


def _build_session_filters(filters: dict, user: str) -> tuple[dict, dict]:
	query_filters: dict[str, Any] = {}
	branches, restricted = _branch_scope(user, filters.get("branch"))
	if restricted:
		query_filters["branch"] = ["in", branches or ["__vetedge_no_permitted_branch__"]]
	elif branches:
		query_filters["branch"] = branches[0]

	for fieldname in ("company", "customer", "animal"):
		value = cstr(filters.get(fieldname) or "").strip()
		if value:
			query_filters[fieldname] = value

	status = cstr(filters.get("status") or "").strip()
	if status:
		if status not in ALLOWED_SESSION_STATUSES:
			frappe.throw(_("Invalid billing session status."), frappe.ValidationError)
		query_filters["status"] = status

	from_date = cstr(filters.get("from_date") or "").strip()
	to_date = cstr(filters.get("to_date") or "").strip()
	if from_date or to_date:
		start_date = getdate(from_date or to_date)
		end_date = getdate(to_date or from_date)
		if start_date > end_date:
			frappe.throw(_("From Date cannot be after To Date."), frappe.ValidationError)
		query_filters["creation"] = ["between", [f"{start_date} 00:00:00", f"{end_date} 23:59:59"]]

	return query_filters, {
		"restricted": restricted,
		"permitted_branches": branches or [],
		"selected_branch": cstr(filters.get("branch") or "").strip(),
	}


def _normalize_activity_filter(value: str | None) -> str:
	activity = cstr(value or DEFAULT_ACTIVITY_FILTER).strip().lower()
	if activity not in ALLOWED_ACTIVITY_FILTERS:
		frappe.throw(_("Invalid Billing Center activity filter."), frappe.ValidationError)
	return activity


def _activity_query(filters: dict) -> tuple[dict, dict | None, str]:
	"""Return query conditions for operational Billing Session activity.

	Actionable Billing includes any session with financial movement or an invoice
	link. Empty sessions remain queryable for diagnostics but do not belong in the
	default operational work queue or Open Sessions KPI.
	"""
	activity = _normalize_activity_filter(filters.get("activity"))
	if activity == "all":
		return {}, None, activity
	if activity == "empty":
		return (
			{
				"total_charges": 0,
				"total_invoiced": 0,
				"total_paid": 0,
				"outstanding_amount": 0,
				"current_draft_invoice": ["is", "not set"],
				"latest_invoice": ["is", "not set"],
			},
			None,
			activity,
		)
	return (
		{},
		{
			"total_charges": ["!=", 0],
			"total_invoiced": ["!=", 0],
			"total_paid": ["!=", 0],
			"outstanding_amount": ["!=", 0],
			"current_draft_invoice": ["is", "set"],
			"latest_invoice": ["is", "set"],
		},
		activity,
	)


def _aggregate(filters: dict, or_filters: dict | None = None) -> dict:
	rows = frappe.get_list(
		BILLING_SESSION_DOCTYPE,
		filters=filters,
		or_filters=or_filters,
		fields=[
			{"COUNT": "*", "as": "session_count"},
			{"SUM": "total_charges", "as": "total_charges"},
			{"SUM": "total_invoiced", "as": "total_invoiced"},
			{"SUM": "total_paid", "as": "total_paid"},
			{"SUM": "outstanding_amount", "as": "outstanding_amount"},
		],
		limit_page_length=1,
	)
	row = rows[0] if rows else {}
	return {
		"session_count": cint(row.get("session_count")),
		"total_charges": flt(row.get("total_charges")),
		"total_invoiced": flt(row.get("total_invoiced")),
		"total_paid": flt(row.get("total_paid")),
		"outstanding_amount": flt(row.get("outstanding_amount")),
	}


def _count(filters: dict, or_filters: dict | None = None) -> int:
	rows = frappe.get_list(
		BILLING_SESSION_DOCTYPE,
		filters=filters,
		or_filters=or_filters,
		fields=[{"COUNT": "*", "as": "total"}],
		limit_page_length=1,
	)
	return cint(rows[0].get("total")) if rows else 0


def _company_currency(company: str | None) -> str:
	if company and frappe.db.exists("Company", company):
		return cstr(frappe.db.get_value("Company", company, "default_currency") or "")
	return cstr(frappe.defaults.get_global_default("currency") or "NGN")


def _patient_display_map(patient_ids: list[str]) -> dict[str, str]:
	patient_ids = sorted({cstr(value).strip() for value in patient_ids if cstr(value).strip()})
	if not patient_ids:
		return {}

	# Patient ids come only from Billing Sessions already visible to the caller.
	# This lookup decorates those known ids with friendly names; it never expands
	# the caller's Billing Session scope or returns unrelated patient records.
	rows = frappe.get_all(
		PATIENT_DOCTYPE,
		filters={"name": ["in", patient_ids]},
		fields=["name", "patient_name"],
		limit_page_length=min(len(patient_ids), PAGE_LENGTH_MAX),
	)
	return {
		cstr(row.get("name") or "").strip(): cstr(row.get("patient_name") or row.get("name") or "").strip()
		for row in rows
		if cstr(row.get("name") or "").strip()
	}


def _decorate_patient_names(rows: list[dict]) -> list[dict]:
	labels = _patient_display_map([row.get("animal") for row in rows])
	for row in rows:
		patient_id = cstr(row.get("animal") or "").strip()
		patient_name = labels.get(patient_id) or patient_id
		row["patient_name"] = patient_name
		row["patient_display"] = f"{patient_name} ({patient_id})" if patient_name and patient_id and patient_name != patient_id else patient_id
	return rows


def _patient_link_options(base_filters: dict, search: str, or_filters: dict | None = None) -> list[dict]:
	search = cstr(search or "").strip()
	if search:
		pattern = f"%{search}%"
		candidate_rows = frappe.get_all(
			PATIENT_DOCTYPE,
			filters={},
			or_filters={"patient_name": ["like", pattern], "name": ["like", pattern]},
			fields=["name", "patient_name"],
			order_by="patient_name asc, name asc",
			limit_page_length=PATIENT_SEARCH_CANDIDATE_LIMIT,
		)
		candidate_ids = [cstr(row.get("name") or "").strip() for row in candidate_rows if cstr(row.get("name") or "").strip()]
		if not candidate_ids:
			return []
		visible_filters = dict(base_filters)
		visible_filters["animal"] = ["in", candidate_ids]
		visible_rows = frappe.get_list(
			BILLING_SESSION_DOCTYPE,
			filters=visible_filters,
			or_filters=or_filters,
			fields=["animal"],
			group_by="animal",
			page_length=20,
		)
		visible_ids = {cstr(row.get("animal") or "").strip() for row in visible_rows if cstr(row.get("animal") or "").strip()}
		return [
			{
				"value": patient_id,
				"label": f"{patient_name} ({patient_id})" if patient_name and patient_name != patient_id else patient_id,
			}
			for row in candidate_rows
			if (patient_id := cstr(row.get("name") or "").strip()) in visible_ids
			for patient_name in [cstr(row.get("patient_name") or patient_id).strip()]
		][:20]

	visible_filters = dict(base_filters)
	visible_filters["animal"] = ["is", "set"]
	visible_rows = frappe.get_list(
		BILLING_SESSION_DOCTYPE,
		filters=visible_filters,
		or_filters=or_filters,
		fields=["animal"],
		order_by="animal asc",
		group_by="animal",
		page_length=20,
	)
	patient_ids = [cstr(row.get("animal") or "").strip() for row in visible_rows if cstr(row.get("animal") or "").strip()]
	labels = _patient_display_map(patient_ids)
	return [
		{
			"value": patient_id,
			"label": f"{labels.get(patient_id)} ({patient_id})" if labels.get(patient_id) and labels.get(patient_id) != patient_id else patient_id,
		}
		for patient_id in patient_ids
	]


@frappe.whitelist()
def get_billing_center(filters: str | dict | None = None, start: int = 0, page_length: int = PAGE_LENGTH_DEFAULT) -> dict:
	"""Return a bounded, permission-aware Billing Session management read model.

	Billing Session is the authoritative veterinary billing anchor. This endpoint
	does not infer unrelated ERPNext invoices into a Branch and does not create,
	submit, cancel, amend, allocate, or otherwise mutate accounting documents.
	"""
	user = _require_billing_center_access()
	parsed = _parse_filters(filters)
	base_filters, scope = _build_session_filters(parsed, user)
	activity_filters, activity_or_filters, activity = _activity_query(parsed)
	session_filters = {**base_filters, **activity_filters}
	start, page_length = _page_values(start, page_length)

	rows = frappe.get_list(
		BILLING_SESSION_DOCTYPE,
		filters=session_filters,
		or_filters=activity_or_filters,
		fields=[
			"name",
			"customer",
			"animal",
			"company",
			"branch",
			"status",
			"payment_gate_mode",
			"current_draft_invoice",
			"latest_invoice",
			"total_charges",
			"total_invoiced",
			"total_paid",
			"outstanding_amount",
			"payment_status",
			"source_context_doctype",
			"source_context_name",
			"creation",
			"modified",
		],
		order_by="modified desc",
		start=start,
		page_length=page_length,
	)
	rows = _decorate_patient_names(rows)

	summary = _aggregate(session_filters, activity_or_filters)
	open_filters = dict(session_filters)
	open_filters["status"] = ["in", list(OPEN_SESSION_STATUSES)]
	summary["open_sessions"] = _count(open_filters, activity_or_filters)
	summary["outstanding_sessions"] = _count({**session_filters, "outstanding_amount": [">", 0]}, activity_or_filters)
	empty_filters, _, _ = _activity_query({"activity": "empty"})
	summary["no_billing_activity_sessions"] = _count({**base_filters, **empty_filters})

	scope["activity"] = activity
	company = cstr(parsed.get("company") or "").strip()
	return {
		"rows": rows,
		"total": summary["session_count"],
		"start": start,
		"page_length": page_length,
		"summary": summary,
		"scope": scope,
		"currency": _company_currency(company or None),
		"capabilities": {
			"customer": bool(frappe.has_permission("Customer", "read")),
			"sales_invoice": bool(frappe.has_permission("Sales Invoice", "read")),
			"payment_entry": bool(frappe.has_permission("Payment Entry", "read")),
			"billing_session": True,
		},
		"boundary": _("Billing Center shows Veterinary Billing Sessions and their linked invoice state. ERPNext accounting documents remain authoritative and are opened in their native workflows."),
	}


@frappe.whitelist()
def get_billing_center_link_options(
	fieldname: str,
	query: str = "",
	company: str | None = None,
	branch: str | None = None,
	customer: str | None = None,
	activity: str | None = None,
) -> list[dict]:
	"""Return only values relevant to the caller's permitted billing scope."""
	user = _require_billing_center_access()
	field = cstr(fieldname or "").strip()
	if field not in LINK_FIELDS:
		frappe.throw(_("Unsupported Billing Center filter field."), frappe.ValidationError)

	context = {
		"company": cstr(company or "").strip(),
		"branch": cstr(branch or "").strip(),
	}
	if field == "animal":
		context["customer"] = cstr(customer or "").strip()

	base_filters, scope = _build_session_filters(context, user)
	activity_filters, activity_or_filters, _ = _activity_query({"activity": activity or DEFAULT_ACTIVITY_FILTER})
	base_filters.update(activity_filters)
	search = cstr(query or "").strip()

	# Do not overwrite the server-authoritative Branch restriction with a text
	# search filter. Restricted users search only their assigned Branch names.
	if field == "branch" and scope.get("restricted"):
		needle = search.casefold()
		return [
			{"value": value, "label": value}
			for value in scope.get("permitted_branches") or []
			if not needle or needle in value.casefold()
		][:20]

	if field == "animal":
		return _patient_link_options(base_filters, search, activity_or_filters)

	if search:
		base_filters[field] = ["like", f"%{search}%"]
	else:
		base_filters[field] = ["is", "set"]

	rows = frappe.get_list(
		BILLING_SESSION_DOCTYPE,
		filters=base_filters,
		or_filters=activity_or_filters,
		fields=[field],
		order_by=f"{field} asc",
		group_by=field,
		page_length=20,
	)
	values = []
	seen = set()
	for row in rows:
		value = cstr(row.get(field) or "").strip()
		if not value or value in seen:
			continue
		seen.add(value)
		values.append({"value": value, "label": value})
	return values
