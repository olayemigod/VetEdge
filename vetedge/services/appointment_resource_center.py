from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import add_days, cint, cstr, get_datetime, getdate

from vetedge.coreedge_adapter import get_current_vetedge_branch
from vetedge.services.appointment_actions import build_appointment_action_state
from vetedge.services.permissions import can_access_branch_data

APPOINTMENT_DOCTYPE = "Veterinary Appointment"
PAGE_LENGTH_MAX = 100
APPOINTMENT_LIST_FIELDS = (
	"name",
	"appointment_datetime",
	"patient",
	"primary_owner",
	"branch",
	"practitioner",
	"practitioner_name",
	"appointment_type",
	"consultation_type",
	"status",
	"modified",
)
APPOINTMENT_SORT_FIELDS = frozenset(
	{
		"name",
		"appointment_datetime",
		"patient",
		"primary_owner",
		"branch",
		"practitioner",
		"practitioner_name",
		"appointment_type",
		"consultation_type",
		"status",
		"modified",
	}
)
DEFAULT_SORT_BY = "appointment_datetime"
DEFAULT_SORT_ORDER = "asc"
SEARCH_FIELDS = (
	"name",
	"appointment_title",
	"patient",
	"primary_owner",
	"practitioner_name",
	"status",
	"appointment_type",
)
COLUMN_DEFINITIONS = (
	("appointment_datetime", "Appointment Date/Time", "Datetime"),
	("patient", "Patient", "Link"),
	("primary_owner", "Primary Owner", "Link"),
	("branch", "Branch", "Link"),
	("practitioner_name", "Practitioner", "Data"),
	("appointment_type", "Appointment Type", "Select"),
	("consultation_type", "Consultation Type", "Link"),
	("status", "Status", "Select"),
	("name", "ID", "Data"),
)


def _require_access() -> None:
	if frappe.session.user == "Guest":
		frappe.throw(_("Authentication required."), frappe.PermissionError)
	if not frappe.has_permission(APPOINTMENT_DOCTYPE, "read"):
		frappe.throw(_("You are not permitted to view Veterinary Appointments."), frappe.PermissionError)


def _clean(value: Any) -> str:
	return cstr(value or "").strip()


def _current_branch() -> str:
	try:
		branch = _clean(get_current_vetedge_branch())
	except Exception:
		branch = ""
	return "" if branch.lower() in {"all", "all branches"} else branch


def _selected_branch(branch: str) -> str:
	requested = _clean(branch)
	current = _current_branch()
	if requested and current and requested != current:
		frappe.throw(
			_("Selected Branch is outside the current Veterinary branch context."),
			frappe.PermissionError,
		)
	selected = requested or current
	if selected:
		can_access_branch_data(frappe.session.user, selected, raise_exception=True)
	return selected


def _allowed_select_values(fieldname: str) -> set[str]:
	meta = frappe.get_meta(APPOINTMENT_DOCTYPE)
	field = meta.get_field(fieldname)
	return {value.strip() for value in cstr(field.options or "").splitlines() if value.strip()} if field else set()


def _validated_select(fieldname: str, value: str) -> str:
	selected = _clean(value)
	if not selected:
		return ""
	allowed = _allowed_select_values(fieldname)
	if allowed and selected not in allowed:
		frappe.throw(_("Invalid {0} filter.").format(fieldname.replace("_", " ").title()), frappe.ValidationError)
	return selected


def _validated_dates(from_date: str, to_date: str) -> tuple[Any | None, Any | None]:
	start_date = getdate(from_date) if _clean(from_date) else None
	end_date = getdate(to_date) if _clean(to_date) else None
	if start_date and end_date and start_date > end_date:
		frappe.throw(_("From Date cannot be after To Date."), frappe.ValidationError)
	start_datetime = get_datetime(f"{start_date} 00:00:00") if start_date else None
	end_datetime = get_datetime(f"{add_days(end_date, 1)} 00:00:00") if end_date else None
	return start_datetime, end_datetime


def _filters(
	*,
	branch: str = "",
	patient: str = "",
	owner: str = "",
	practitioner: str = "",
	status: str = "",
	appointment_type: str = "",
	consultation_type: str = "",
	from_date: str = "",
	to_date: str = "",
) -> list[list[Any]]:
	filters: list[list[Any]] = []
	selected_branch = _selected_branch(branch)
	if selected_branch:
		filters.append([APPOINTMENT_DOCTYPE, "branch", "=", selected_branch])

	for fieldname, value in (
		("patient", patient),
		("primary_owner", owner),
		("practitioner", practitioner),
		("consultation_type", consultation_type),
	):
		selected = _clean(value)
		if selected:
			filters.append([APPOINTMENT_DOCTYPE, fieldname, "=", selected])

	selected_status = _validated_select("status", status)
	if selected_status:
		filters.append([APPOINTMENT_DOCTYPE, "status", "=", selected_status])
	selected_type = _validated_select("appointment_type", appointment_type)
	if selected_type:
		filters.append([APPOINTMENT_DOCTYPE, "appointment_type", "=", selected_type])

	start_datetime, end_datetime = _validated_dates(from_date, to_date)
	if start_datetime:
		filters.append([APPOINTMENT_DOCTYPE, "appointment_datetime", ">=", start_datetime])
	if end_datetime:
		filters.append([APPOINTMENT_DOCTYPE, "appointment_datetime", "<", end_datetime])
	return filters


def _or_filters(search: str) -> list[list[Any]] | None:
	query = _clean(search)
	if not query:
		return None
	pattern = f"%{query}%"
	return [[APPOINTMENT_DOCTYPE, fieldname, "like", pattern] for fieldname in SEARCH_FIELDS]


def _sort(sort_by: str, sort_order: str) -> tuple[str, str]:
	fieldname = _clean(sort_by) or DEFAULT_SORT_BY
	if fieldname not in APPOINTMENT_SORT_FIELDS:
		fieldname = DEFAULT_SORT_BY
	order = _clean(sort_order).lower()
	if order not in {"asc", "desc"}:
		order = DEFAULT_SORT_ORDER
	return fieldname, order


def _count(filters: list[list[Any]], or_filters: list[list[Any]] | None) -> int:
	rows = frappe.get_list(
		APPOINTMENT_DOCTYPE,
		fields=[{"COUNT": "*", "as": "total"}],
		filters=filters,
		or_filters=or_filters,
		limit_page_length=1,
	)
	return cint(rows[0].get("total")) if rows else 0


def _display_maps(rows: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
	patient_names: dict[str, str] = {}
	owner_names: dict[str, str] = {}
	patient_ids = sorted({_clean(row.get("patient")) for row in rows if _clean(row.get("patient"))})
	owner_ids = sorted({_clean(row.get("primary_owner")) for row in rows if _clean(row.get("primary_owner"))})

	if patient_ids and frappe.has_permission("Veterinary Patient", "read"):
		for row in frappe.get_list(
			"Veterinary Patient",
			fields=["name", "patient_name"],
			filters={"name": ["in", patient_ids]},
			page_length=len(patient_ids),
		):
			patient_names[row.name] = _clean(row.get("patient_name")) or row.name

	if owner_ids and frappe.has_permission("Customer", "read"):
		for row in frappe.get_list(
			"Customer",
			fields=["name", "customer_name"],
			filters={"name": ["in", owner_ids]},
			page_length=len(owner_ids),
		):
			owner_names[row.name] = _clean(row.get("customer_name")) or row.name
	return patient_names, owner_names


def _decorate_rows(rows: list[dict]) -> list[dict]:
	patient_names, owner_names = _display_maps(rows)
	for row in rows:
		row["_display"] = {
			"patient": patient_names.get(_clean(row.get("patient")), _clean(row.get("patient"))),
			"primary_owner": owner_names.get(_clean(row.get("primary_owner")), _clean(row.get("primary_owner"))),
		}
		doc = frappe.get_cached_doc(APPOINTMENT_DOCTYPE, row.name)
		doc.check_permission("read")
		row["_appointment_action_state"] = build_appointment_action_state(doc)
	return rows


def _columns() -> list[dict[str, Any]]:
	return [
		{
			"fieldname": fieldname,
			"label": _(label),
			"fieldtype": fieldtype,
			"sortable": fieldname in APPOINTMENT_SORT_FIELDS,
		}
		for fieldname, label, fieldtype in COLUMN_DEFINITIONS
	]


@frappe.whitelist()
def get_appointment_page(
	search: str = "",
	start: int = 0,
	page_length: int = 25,
	branch: str = "",
	patient: str = "",
	owner: str = "",
	practitioner: str = "",
	status: str = "",
	appointment_type: str = "",
	consultation_type: str = "",
	from_date: str = "",
	to_date: str = "",
	sort_by: str = DEFAULT_SORT_BY,
	sort_order: str = DEFAULT_SORT_ORDER,
) -> dict[str, Any]:
	"""Return the permission-aware Appointments worklist with bounded filters and sorting."""
	_require_access()
	filters = _filters(
		branch=branch,
		patient=patient,
		owner=owner,
		practitioner=practitioner,
		status=status,
		appointment_type=appointment_type,
		consultation_type=consultation_type,
		from_date=from_date,
		to_date=to_date,
	)
	or_filters = _or_filters(search)
	sort_field, order = _sort(sort_by, sort_order)
	page_length = min(max(cint(page_length) or 25, 1), PAGE_LENGTH_MAX)
	start = max(cint(start), 0)

	rows = frappe.get_list(
		APPOINTMENT_DOCTYPE,
		fields=list(APPOINTMENT_LIST_FIELDS),
		filters=filters,
		or_filters=or_filters,
		order_by=f"{sort_field} {order}, name asc",
		start=start,
		page_length=page_length,
	)
	rows = _decorate_rows(rows)
	current_branch = _selected_branch(branch)
	can_create = bool(frappe.has_permission(APPOINTMENT_DOCTYPE, "create"))
	can_edit = bool(frappe.has_permission(APPOINTMENT_DOCTYPE, "write"))

	return {
		"resource": "appointments",
		"doctype": APPOINTMENT_DOCTYPE,
		"title": _("Appointments"),
		"subtitle": _("Filter, sort and manage appointments without leaving the Veterinary workspace."),
		"columns": _columns(),
		"rows": rows,
		"start": start,
		"page_length": page_length,
		"total": _count(filters, or_filters),
		"can_create": can_create,
		"can_quick_edit": can_edit,
		"can_delete": False,
		"unsupported_required_fields": [],
		"full_form_route": "/desk/veterinary-appointment",
		"context_branch": current_branch,
		"summary_label": _("Branch Scope"),
		"summary_value": current_branch or _("All permitted branches"),
		"sort_by": sort_field,
		"sort_order": order,
	}
