from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services.permissions import (
	get_assigned_branches,
	get_current_user,
	get_system_users,
	get_veterinary_doctor_users,
	is_internal_staff_user,
	is_portal_owner_user,
	user_has_global_branch_access,
)
from vetedge.services.platform_access import require_vetedge_platform_access
from vetedge.services.portal_access import require_internal_user

PAGE_LENGTH_MAX = 100
RESOURCE_CONFIG: dict[str, dict[str, Any]] = {
	"user-assignments": {
		"doctype": "Branch User Assignment",
		"title": _("Branch User Access"),
		"singular": _("User Branch Assignment"),
		"subtitle": _("Control which Veterinary Branches each internal user can access."),
		"person_field": "user",
		"person_label": _("User"),
	},
	"practitioner-assignments": {
		"doctype": "Branch Practitioner Assignment",
		"title": _("Practitioner Coverage"),
		"singular": _("Practitioner Branch Assignment"),
		"subtitle": _("Assign Veterinary Doctors to the Branches where they may practise."),
		"person_field": "practitioner",
		"person_label": _("Practitioner"),
	},
}


def _current_user() -> str | None:
	return get_current_user()


def _resource(resource: str) -> dict[str, Any]:
	key = cstr(resource).strip().lower()
	config = RESOURCE_CONFIG.get(key)
	if not config:
		frappe.throw(_("This Branch access resource is not available."), frappe.PermissionError)
	if not frappe.db.exists("DocType", config["doctype"]):
		frappe.throw(_("{0} is not installed on this site.").format(config["doctype"]))
	return {"key": key, **config}


def _allowed_branches(user: str | None = None) -> list[str] | None:
	"""None means explicit global access; an empty list intentionally fails closed."""
	user = user or _current_user()
	if user_has_global_branch_access(user):
		return None
	if not user or user == "Guest" or is_portal_owner_user(user) or not is_internal_staff_user(user):
		return []
	return sorted({cstr(branch).strip() for branch in get_assigned_branches(user) if cstr(branch).strip()})


def _assert_branch_access(branch: str | None, user: str | None = None) -> None:
	branch = cstr(branch).strip()
	if not branch:
		frappe.throw(_("Branch is required for every Branch access assignment."), frappe.ValidationError)

	allowed = _allowed_branches(user)
	if allowed is None:
		return
	if not allowed:
		frappe.throw(
			_("You do not have an assigned Veterinary Branch for Branch access management."),
			frappe.PermissionError,
		)
	if branch not in allowed:
		frappe.throw(_("You do not have access to manage assignments for the selected Branch."), frappe.PermissionError)


def _require_permission(config: dict[str, Any], permission_type: str) -> None:
	require_internal_user()
	if not frappe.has_permission(config["doctype"], permission_type):
		frappe.throw(
			_("You are not permitted to {0} {1}.").format(permission_type, config["title"]),
			frappe.PermissionError,
		)


def _parse_object(value: str | dict | None) -> dict[str, Any]:
	if not value:
		return {}
	if isinstance(value, dict):
		return value
	parsed = frappe.parse_json(value)
	if not isinstance(parsed, dict):
		frappe.throw(_("Expected a JSON object."), frappe.ValidationError)
	return parsed


def _scope_filters(filters: str | dict | None = None) -> tuple[dict[str, Any], bool]:
	payload = _parse_object(filters)
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

	disabled = payload.get("disabled")
	if disabled not in (None, ""):
		query_filters["disabled"] = cint(disabled)
	return query_filters, True


def _count(doctype: str, filters: dict[str, Any], or_filters: list | None = None) -> int:
	rows = frappe.get_list(
		doctype,
		fields=[{"COUNT": "*", "as": "total"}],
		filters=filters,
		or_filters=or_filters,
		limit_page_length=1,
	)
	return cint(rows[0].get("total")) if rows else 0


def _columns(config: dict[str, Any]) -> list[dict[str, Any]]:
	return [
		{
			"fieldname": config["person_field"],
			"label": config["person_label"],
			"fieldtype": "Link",
			"options": "User",
		},
		{"fieldname": "branch", "label": _("Branch"), "fieldtype": "Link", "options": "Branch"},
		{"fieldname": "disabled", "label": _("Disabled"), "fieldtype": "Check"},
		{"fieldname": "modified", "label": _("Modified"), "fieldtype": "Datetime"},
	]


def _form_schema(config: dict[str, Any]) -> dict[str, Any]:
	return {
		"tabs": [
			{
				"key": "assignment",
				"label": _("Assignment"),
				"description": config["subtitle"],
				"sections": [
					{
						"key": "assignment-details",
						"label": "",
						"description": "",
						"columns": 2,
						"fields": [
							{
								"fieldname": config["person_field"],
								"fieldtype": "Link",
								"label": config["person_label"],
								"options": "User",
								"reqd": 1,
								"description": _("Only eligible internal users are returned by search."),
							},
							{
								"fieldname": "branch",
								"fieldtype": "Link",
								"label": _("Branch"),
								"options": "Branch",
								"reqd": 1,
								"description": _("Only Branches you are authorised to manage are available."),
							},
							{
								"fieldname": "disabled",
								"fieldtype": "Check",
								"label": _("Disabled"),
								"reqd": 0,
								"default": 0,
							},
						],
					}
				],
			}
		]
	}


def _permissions(config: dict[str, Any], doc=None) -> dict[str, bool]:
	allowed = _allowed_branches()
	branch_scope_available = allowed is None or bool(allowed)
	permissions = {
		"read": bool(doc.has_permission("read") if doc else frappe.has_permission(config["doctype"], "read")),
		"create": bool(frappe.has_permission(config["doctype"], "create")),
		"write": bool(doc.has_permission("write") if doc else frappe.has_permission(config["doctype"], "write")),
		"delete": bool(doc.has_permission("delete") if doc else frappe.has_permission(config["doctype"], "delete")),
	}
	if not branch_scope_available:
		return {key: False for key in permissions}
	if doc and allowed is not None and cstr(doc.get("branch")).strip() not in allowed:
		return {key: False for key in permissions}
	return permissions


def _document_payload(config: dict[str, Any], doc, *, is_new: bool = False) -> dict[str, Any]:
	return {
		"resource": config["key"],
		"doctype": config["doctype"],
		"name": None if is_new else doc.name,
		"is_new": is_new,
		"title": config["singular"] if is_new else (doc.get(config["person_field"]) or doc.name),
		"schema": _form_schema(config),
		"values": {
			config["person_field"]: doc.get(config["person_field"]),
			"branch": doc.get("branch"),
			"disabled": cint(doc.get("disabled")),
		},
		"permissions": _permissions(config, None if is_new else doc),
		"modified": None if is_new else doc.modified,
	}


def _validated_values(config: dict[str, Any], values: str | dict) -> dict[str, Any]:
	payload = _parse_object(values)
	person_field = config["person_field"]
	person = cstr(payload.get(person_field)).strip()
	if not person:
		frappe.throw(_("{0} is required.").format(config["person_label"]), frappe.ValidationError)
	if not frappe.db.exists("User", person):
		frappe.throw(_("User {0} does not exist.").format(person), frappe.ValidationError)

	branch = cstr(payload.get("branch")).strip()
	_assert_branch_access(branch)
	if not frappe.db.exists("Branch", branch):
		frappe.throw(_("Branch {0} does not exist.").format(branch), frappe.ValidationError)

	return {
		person_field: person,
		"branch": branch,
		"disabled": cint(payload.get("disabled") or 0),
	}


@frappe.whitelist()
def get_branch_access_page(
	resource: str,
	search: str = "",
	filters: str | dict | None = None,
	start: int = 0,
	page_length: int = 25,
) -> dict[str, Any]:
	config = _resource(resource)
	_require_permission(config, "read")
	query_filters, branch_scope_available = _scope_filters(filters)
	start = max(cint(start), 0)
	page_length = min(max(cint(page_length) or 25, 1), PAGE_LENGTH_MAX)

	if not branch_scope_available:
		return {
			"resource": config["key"],
			"title": config["title"],
			"singular": config["singular"],
			"subtitle": config["subtitle"],
			"columns": _columns(config),
			"rows": [],
			"total": 0,
			"start": start,
			"page_length": page_length,
			"permissions": _permissions(config),
			"branch_scope_empty": True,
		}

	text = cstr(search).strip()
	or_filters = None
	if text:
		or_filters = [
			[config["doctype"], config["person_field"], "like", f"%{text}%"],
			[config["doctype"], "branch", "like", f"%{text}%"],
		]

	rows = frappe.get_list(
		config["doctype"],
		fields=["name", config["person_field"], "branch", "disabled", "modified"],
		filters=query_filters,
		or_filters=or_filters,
		order_by="modified desc",
		start=start,
		page_length=page_length,
	)
	return {
		"resource": config["key"],
		"title": config["title"],
		"singular": config["singular"],
		"subtitle": config["subtitle"],
		"columns": _columns(config),
		"rows": rows,
		"total": _count(config["doctype"], query_filters, or_filters),
		"start": start,
		"page_length": page_length,
		"permissions": _permissions(config),
		"branch_scope_empty": False,
	}


@frappe.whitelist()
def get_branch_access_document(resource: str, name: str | None = None) -> dict[str, Any]:
	config = _resource(resource)
	if name:
		_require_permission(config, "read")
		doc = frappe.get_doc(config["doctype"], name)
		doc.check_permission("read")
		_assert_branch_access(doc.get("branch"))
		return _document_payload(config, doc)

	_require_permission(config, "create")
	allowed = _allowed_branches()
	if allowed == []:
		frappe.throw(
			_("You do not have an assigned Veterinary Branch for Branch access management."),
			frappe.PermissionError,
		)
	doc = frappe.new_doc(config["doctype"])
	if allowed is not None and len(allowed) == 1:
		doc.branch = allowed[0]
	return _document_payload(config, doc, is_new=True)


@frappe.whitelist()
def save_branch_access_document(
	resource: str,
	values: str | dict,
	name: str | None = None,
	modified: str | None = None,
) -> dict[str, Any]:
	config = _resource(resource)
	require_internal_user()
	require_vetedge_platform_access(
		action="save_branch_access_assignment",
		reference_doctype=config["doctype"],
		reference_name=name,
	)
	payload = _validated_values(config, values)

	if name:
		_require_permission(config, "write")
		doc = frappe.get_doc(config["doctype"], name)
		doc.check_permission("write")
		_assert_branch_access(doc.get("branch"))
		if modified and cstr(doc.modified) != cstr(modified):
			frappe.throw(
				_("This Branch access assignment changed after you opened it. Reload before saving."),
				frappe.TimestampMismatchError,
			)
	else:
		_require_permission(config, "create")
		doc = frappe.new_doc(config["doctype"])

	for fieldname, value in payload.items():
		doc.set(fieldname, value)
	if doc.is_new():
		doc.insert()
	else:
		doc.save()
	return _document_payload(config, doc)


@frappe.whitelist()
def delete_branch_access_document(resource: str, name: str) -> dict[str, Any]:
	config = _resource(resource)
	_require_permission(config, "delete")
	require_vetedge_platform_access(
		action="delete_branch_access_assignment",
		reference_doctype=config["doctype"],
		reference_name=name,
	)
	doc = frappe.get_doc(config["doctype"], name)
	doc.check_permission("delete")
	_assert_branch_access(doc.get("branch"))
	frappe.delete_doc(config["doctype"], name)
	return {"deleted": True, "name": name}


def _user_search_options(rows: list) -> list[dict[str, Any]]:
	options: list[dict[str, Any]] = []
	for row in rows or []:
		if isinstance(row, (list, tuple)):
			value = row[0] if row else ""
			label = row[1] if len(row) > 1 else value
		else:
			value = row.get("name")
			label = row.get("full_name") or value
		value = cstr(value).strip()
		if value:
			options.append(
				{
					"value": value,
					"label": cstr(label).strip() or value,
					"description": value if cstr(label).strip() and cstr(label).strip() != value else "",
				}
			)
	return options


@frappe.whitelist()
def search_branch_access_link(
	resource: str,
	fieldname: str,
	query: str = "",
	page_length: int = 20,
) -> list[dict[str, Any]]:
	config = _resource(resource)
	_require_permission(config, "read")
	fieldname = cstr(fieldname).strip()
	query = cstr(query).strip()
	page_length = min(max(cint(page_length) or 20, 1), 50)

	if fieldname == "branch":
		if not frappe.has_permission("Branch", "read"):
			return []
		allowed = _allowed_branches()
		if allowed == []:
			return []
		filters: dict[str, Any] = {}
		meta = frappe.get_meta("Branch")
		if allowed is not None:
			filters["name"] = ["in", allowed]
		if meta.has_field("disabled"):
			filters["disabled"] = 0
		or_filters = [["Branch", "name", "like", f"%{query}%"]] if query else None
		rows = frappe.get_list(
			"Branch",
			fields=["name"],
			filters=filters,
			or_filters=or_filters,
			order_by="name asc",
			page_length=page_length,
		)
		return [{"value": row.name, "label": row.name, "description": ""} for row in rows]

	if fieldname != config["person_field"]:
		return []
	if config["key"] == "practitioner-assignments":
		rows = get_veterinary_doctor_users("User", query, "name", 0, page_length, {})
	else:
		rows = get_system_users("User", query, "name", 0, page_length, {})
	return _user_search_options(rows)
