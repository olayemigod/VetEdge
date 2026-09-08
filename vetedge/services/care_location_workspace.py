from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services.permissions import (
	get_assigned_branches,
	get_current_user,
	is_internal_staff_user,
	is_portal_owner_user,
	user_has_global_branch_access,
)
from vetedge.services.platform_access import require_vetedge_platform_access
from vetedge.services.portal_access import require_internal_user

DOCTYPE = "Veterinary Care Location"
PAGE_LENGTH_MAX = 100
LOCATION_TYPES = {"Ward", "Kennel", "Cage", "ICU", "Isolation", "Recovery", "General"}
STATUSES = {"Available", "Occupied", "Cleaning", "Maintenance", "Inactive"}
FORM_FIELDS = ("location_name", "branch", "location_type", "status", "capacity", "enabled", "notes")


def _user() -> str | None:
	return get_current_user()


def _allowed_branches(user: str | None = None) -> list[str] | None:
	"""None means explicit global access. Empty list means fail closed."""
	user = user or _user()
	if user_has_global_branch_access(user):
		return None
	if not user or user == "Guest" or is_portal_owner_user(user) or not is_internal_staff_user(user):
		return []
	return sorted({cstr(branch).strip() for branch in get_assigned_branches(user) if cstr(branch).strip()})


def _require_permission(permission_type: str) -> None:
	require_internal_user()
	if not frappe.has_permission(DOCTYPE, permission_type):
		frappe.throw(_("You are not permitted to {0} Veterinary Care Locations.").format(permission_type), frappe.PermissionError)


def _assert_branch_access(branch: str | None, user: str | None = None) -> None:
	branch = cstr(branch).strip()
	if not branch:
		frappe.throw(_("Branch is required for every Veterinary Care Location."), frappe.ValidationError)
	allowed = _allowed_branches(user)
	if allowed is None:
		return
	if not allowed:
		frappe.throw(_("You do not have an assigned Veterinary Branch for Care Location management."), frappe.PermissionError)
	if branch not in allowed:
		frappe.throw(_("You do not have access to the selected Care Location Branch."), frappe.PermissionError)


def _serialize_field(meta, fieldname: str) -> dict[str, Any]:
	field = meta.get_field(fieldname)
	if not field:
		return {}
	return {
		"fieldname": field.fieldname,
		"fieldtype": field.fieldtype,
		"label": field.label or field.fieldname.replace("_", " ").title(),
		"options": field.options or "",
		"description": field.description or "",
		"default": field.default,
		"reqd": cint(field.reqd),
		"read_only": cint(field.read_only),
		"hidden": cint(field.hidden),
	}


def _schema() -> dict[str, Any]:
	meta = frappe.get_meta(DOCTYPE)
	fields = [_serialize_field(meta, fieldname) for fieldname in FORM_FIELDS]
	return {
		"tabs": [
			{
				"key": "details",
				"label": _("Details"),
				"description": _("Maintain the operational location, Branch and capacity."),
				"sections": [
					{
						"key": "care-location-details",
						"label": "",
						"description": "",
						"columns": 2,
						"fields": [field for field in fields if field],
					}
				],
			}
		]
	}


def _base_permissions(doc=None) -> dict[str, bool]:
	allowed = _allowed_branches()
	branch_scope_available = allowed is None or bool(allowed)
	permissions = {
		"read": bool(doc.has_permission("read") if doc else frappe.has_permission(DOCTYPE, "read")),
		"create": bool(frappe.has_permission(DOCTYPE, "create") and branch_scope_available),
		"write": bool(doc.has_permission("write") if doc else frappe.has_permission(DOCTYPE, "write")),
		"delete": bool(doc.has_permission("delete") if doc else frappe.has_permission(DOCTYPE, "delete")),
	}
	if not branch_scope_available:
		return {key: False for key in permissions}
	if doc and allowed is not None and cstr(doc.get("branch")).strip() not in allowed:
		return {key: False for key in permissions}
	return permissions


def _parse_filters(value: str | dict | None) -> dict[str, Any]:
	if not value:
		return {}
	if isinstance(value, dict):
		return value
	parsed = frappe.parse_json(value)
	if not isinstance(parsed, dict):
		frappe.throw(_("Expected Care Location filters as a JSON object."), frappe.ValidationError)
	return parsed


def _query_filters(filters: str | dict | None = None) -> tuple[dict[str, Any], bool]:
	payload = _parse_filters(filters)
	allowed = _allowed_branches()
	if allowed == []:
		return {}, False
	query_filters: dict[str, Any] = {}
	branch = cstr(payload.get("branch")).strip()
	if branch:
		_assert_branch_access(branch)
		query_filters["branch"] = branch
	elif allowed is not None:
		query_filters["branch"] = ["in", allowed]
	location_type = cstr(payload.get("location_type")).strip()
	if location_type:
		if location_type not in LOCATION_TYPES:
			frappe.throw(_("Invalid Care Location Type."), frappe.ValidationError)
		query_filters["location_type"] = location_type
	status = cstr(payload.get("status")).strip()
	if status:
		if status not in STATUSES:
			frappe.throw(_("Invalid Care Location Status."), frappe.ValidationError)
		query_filters["status"] = status
	enabled = payload.get("enabled")
	if enabled not in (None, ""):
		query_filters["enabled"] = cint(enabled)
	return query_filters, True


def _count(filters: dict[str, Any], or_filters: list | None = None) -> int:
	rows = frappe.get_list(
		DOCTYPE,
		fields=[{"COUNT": "*", "as": "total"}],
		filters=filters,
		or_filters=or_filters,
		limit_page_length=1,
	)
	return cint(rows[0].get("total")) if rows else 0


def _document_payload(doc, *, is_new: bool = False) -> dict[str, Any]:
	values = {fieldname: doc.get(fieldname) for fieldname in FORM_FIELDS}
	return {
		"name": None if is_new else doc.name,
		"is_new": is_new,
		"title": _("New Care Location") if is_new else (doc.get("location_name") or doc.name),
		"schema": _schema(),
		"values": values,
		"permissions": _base_permissions(None if is_new else doc),
		"modified": None if is_new else doc.modified,
	}


@frappe.whitelist()
def get_care_location_page(
	search: str = "",
	filters: str | dict | None = None,
	start: int = 0,
	page_length: int = 25,
) -> dict[str, Any]:
	_require_permission("read")
	query_filters, branch_scope_available = _query_filters(filters)
	start = max(cint(start), 0)
	page_length = min(max(cint(page_length) or 25, 1), PAGE_LENGTH_MAX)
	columns = [
		{"fieldname": "location_name", "label": _("Care Location"), "fieldtype": "Data"},
		{"fieldname": "branch", "label": _("Branch"), "fieldtype": "Link", "options": "Branch"},
		{"fieldname": "location_type", "label": _("Location Type"), "fieldtype": "Data"},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data"},
		{"fieldname": "capacity", "label": _("Capacity"), "fieldtype": "Int"},
		{"fieldname": "enabled", "label": _("Enabled"), "fieldtype": "Check"},
	]
	if not branch_scope_available:
		return {
			"rows": [],
			"total": 0,
			"start": start,
			"page_length": page_length,
			"columns": columns,
			"permissions": _base_permissions(),
			"branch_scope_empty": True,
		}
	text = cstr(search).strip()
	or_filters = None
	if text:
		or_filters = [
			[DOCTYPE, "location_name", "like", f"%{text}%"],
			[DOCTYPE, "branch", "like", f"%{text}%"],
			[DOCTYPE, "location_type", "like", f"%{text}%"],
			[DOCTYPE, "status", "like", f"%{text}%"],
		]
	rows = frappe.get_list(
		DOCTYPE,
		fields=["name", "location_name", "branch", "location_type", "status", "capacity", "enabled", "modified"],
		filters=query_filters,
		or_filters=or_filters,
		order_by="modified desc",
		start=start,
		page_length=page_length,
	)
	return {
		"rows": rows,
		"total": _count(query_filters, or_filters),
		"start": start,
		"page_length": page_length,
		"columns": columns,
		"permissions": _base_permissions(),
		"branch_scope_empty": False,
	}


@frappe.whitelist()
def get_care_location_document(name: str | None = None) -> dict[str, Any]:
	if name:
		_require_permission("read")
		doc = frappe.get_doc(DOCTYPE, name)
		doc.check_permission("read")
		_assert_branch_access(doc.get("branch"))
		return _document_payload(doc)
	_require_permission("create")
	allowed = _allowed_branches()
	if allowed == []:
		frappe.throw(_("You do not have an assigned Veterinary Branch for Care Location management."), frappe.PermissionError)
	doc = frappe.new_doc(DOCTYPE)
	if allowed is not None and len(allowed) == 1:
		doc.branch = allowed[0]
	return _document_payload(doc, is_new=True)


def _validated_values(values: str | dict) -> dict[str, Any]:
	payload = _parse_filters(values)
	location_name = cstr(payload.get("location_name")).strip()
	if not location_name:
		frappe.throw(_("Location Name is required."), frappe.ValidationError)
	branch = cstr(payload.get("branch")).strip()
	_assert_branch_access(branch)
	location_type = cstr(payload.get("location_type") or "General").strip()
	if location_type not in LOCATION_TYPES:
		frappe.throw(_("Invalid Care Location Type."), frappe.ValidationError)
	status = cstr(payload.get("status") or "Available").strip()
	if status not in STATUSES:
		frappe.throw(_("Invalid Care Location Status."), frappe.ValidationError)
	capacity = cint(payload.get("capacity") or 0)
	if capacity < 1:
		frappe.throw(_("Care Location Capacity must be at least 1."), frappe.ValidationError)
	return {
		"location_name": location_name,
		"branch": branch,
		"location_type": location_type,
		"status": status,
		"capacity": capacity,
		"enabled": cint(payload.get("enabled", 1)),
		"notes": cstr(payload.get("notes")),
	}


def _rename_care_location_if_needed(doc, requested_name: str):
	requested_name = cstr(requested_name).strip()
	if not requested_name or requested_name == doc.name:
		return doc
	if frappe.db.exists(DOCTYPE, requested_name):
		frappe.throw(
			_("Another Care Location named {0} already exists.").format(frappe.bold(requested_name)),
			frappe.DuplicateEntryError,
		)
	new_name = frappe.rename_doc(
		DOCTYPE,
		doc.name,
		requested_name,
		force=False,
		merge=False,
		show_alert=False,
	)
	return frappe.get_doc(DOCTYPE, new_name)


@frappe.whitelist()
def save_care_location_document(
	values: str | dict,
	name: str | None = None,
	modified: str | None = None,
) -> dict[str, Any]:
	require_internal_user()
	require_vetedge_platform_access(
		action="save_care_location",
		reference_doctype=DOCTYPE,
		reference_name=name,
	)
	payload = _validated_values(values)
	if name:
		_require_permission("write")
		doc = frappe.get_doc(DOCTYPE, name)
		doc.check_permission("write")
		_assert_branch_access(doc.get("branch"))
		if modified and cstr(doc.modified) != cstr(modified):
			frappe.throw(_("This Care Location changed after you opened it. Reload before saving."), frappe.TimestampMismatchError)
		doc = _rename_care_location_if_needed(doc, payload["location_name"])
		doc.check_permission("write")
	else:
		_require_permission("create")
		doc = frappe.new_doc(DOCTYPE)
	for fieldname, value in payload.items():
		doc.set(fieldname, value)
	if doc.is_new():
		doc.insert()
	else:
		doc.save()
	return _document_payload(doc)


@frappe.whitelist()
def delete_care_location_document(name: str) -> dict[str, Any]:
	_require_permission("delete")
	require_vetedge_platform_access(
		action="delete_care_location",
		reference_doctype=DOCTYPE,
		reference_name=name,
	)
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("delete")
	_assert_branch_access(doc.get("branch"))
	frappe.delete_doc(DOCTYPE, name)
	return {"deleted": True, "name": name}


@frappe.whitelist()
def search_care_location_link(fieldname: str, query: str = "", page_length: int = 20) -> list[dict[str, Any]]:
	require_internal_user()
	if fieldname != "branch":
		return []
	if not frappe.has_permission("Branch", "read"):
		return []
	allowed = _allowed_branches()
	if allowed == []:
		return []
	filters: dict[str, Any] = {}
	if allowed is not None:
		filters["name"] = ["in", allowed]
	meta = frappe.get_meta("Branch")
	title_field = meta.title_field if meta.title_field and meta.has_field(meta.title_field) else "name"
	fields = ["name"] + ([title_field] if title_field != "name" else [])
	text = cstr(query).strip()
	or_filters = None
	if text:
		or_filters = [["Branch", "name", "like", f"%{text}%"]]
		if title_field != "name":
			or_filters.append(["Branch", title_field, "like", f"%{text}%"])
	page_length = min(max(cint(page_length) or 20, 1), 50)
	rows = frappe.get_list(
		"Branch",
		fields=fields,
		filters=filters,
		or_filters=or_filters,
		order_by=f"{title_field} asc",
		page_length=page_length,
	)
	return [
		{
			"value": row.get("name"),
			"label": row.get(title_field) or row.get("name"),
			"description": row.get("name") if title_field != "name" else "",
		}
		for row in rows
	]
