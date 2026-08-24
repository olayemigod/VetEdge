from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services.platform_access import require_vetedge_platform_access
from vetedge.services.portal_access import require_internal_user

PAGE_LENGTH_MAX = 100
ADMIN_ROLES = {"System Manager", "VetEdge Administrator"}

RESOURCE_CONFIG: dict[str, dict[str, Any]] = {
	"notification-preferences": {
		"doctype": "Veterinary Notification Preference",
		"title": _("Notification Preferences"),
		"singular": _("Notification Preference"),
		"subtitle": _("Control event-channel preferences without exposing notification delivery internals to normal users."),
		"mode": "editable",
		"list_fields": ["name", "audience_type", "recipient", "event_key", "email_enabled", "sms_enabled", "whatsapp_enabled", "is_active", "modified"],
		"search_fields": ["audience_type", "recipient", "event_key"],
		"filter_fields": ["audience_type", "event_key", "is_active"],
		"editor_fields": ["audience_type", "recipient", "event_key", "email_enabled", "sms_enabled", "whatsapp_enabled", "is_active"],
	},
	"notification-logs": {
		"doctype": "Veterinary Notification Log",
		"title": _("Notification Delivery Log"),
		"singular": _("Notification Delivery"),
		"subtitle": _("Read-only delivery audit for Veterinary email, SMS and WhatsApp events."),
		"mode": "readonly",
		"list_fields": ["name", "event_key", "channel", "status", "recipient", "created_on", "sent_on", "reference_doctype", "reference_name"],
		"search_fields": ["event_key", "recipient", "reference_doctype", "reference_name"],
		"filter_fields": ["channel", "status", "backend_mode"],
		"detail_fields": ["event_key", "channel", "status", "backend_mode", "recipient", "audience_type", "provider_reference", "created_on", "sent_on", "reference_doctype", "reference_name", "error_message", "payload_preview"],
	},
	"notification-items": {
		"doctype": "Veterinary Notification Item",
		"title": _("Notification Items"),
		"singular": _("Notification Item"),
		"subtitle": _("Read-only administrative view of in-app Veterinary notifications. User actions remain in the notification centre."),
		"mode": "readonly",
		"list_fields": ["name", "notification_title", "status", "priority", "recipient_user", "event_key", "created_on", "reference_doctype", "reference_name"],
		"search_fields": ["notification_title", "message", "recipient_user", "event_key", "reference_name"],
		"filter_fields": ["status", "priority", "recipient_user", "event_key"],
		"detail_fields": ["notification_title", "message", "status", "priority", "recipient_user", "event_key", "created_on", "read_on", "acknowledged_on", "completed_on", "dismissed_on", "archived_on", "reference_doctype", "reference_name", "action_url"],
	},
	"role-bundles": {
		"doctype": "Veterinary Role Bundle",
		"title": _("Role Bundles"),
		"singular": _("Role Bundle"),
		"subtitle": _("Maintain named Veterinary role bundles using validated Frappe Roles."),
		"mode": "role_bundle",
		"list_fields": ["name", "bundle_name", "is_active", "description", "modified"],
		"search_fields": ["bundle_name", "description"],
		"filter_fields": ["is_active"],
		"editor_fields": ["bundle_name", "is_active", "description"],
	},
	"license-profile": {
		"doctype": "Veterinary License Profile",
		"title": _("Legacy License Profile"),
		"singular": _("Legacy License Profile"),
		"subtitle": _("Read-only compatibility view. Platform subscription, activation and access remain CoreEdge responsibilities where CoreEdge is enabled."),
		"mode": "single_readonly",
		"detail_fields": ["plan_name", "subscription_status", "white_label_enabled", "start_date", "expiry_date", "max_branches", "max_users", "enabled_modules"],
		"system_manager_only": True,
	},
}


def _current_roles() -> set[str]:
	return set(frappe.get_roles(frappe.session.user) or [])


def _require_admin(config: dict[str, Any]) -> None:
	require_internal_user()
	roles = _current_roles()
	if config.get("system_manager_only"):
		if "System Manager" not in roles:
			frappe.throw(_("Only System Manager may view the legacy License Profile."), frappe.PermissionError)
		return
	if not roles.intersection(ADMIN_ROLES):
		frappe.throw(_("Veterinary administration access is required."), frappe.PermissionError)


def _resource(resource: str) -> dict[str, Any]:
	key = cstr(resource).strip().lower()
	config = RESOURCE_CONFIG.get(key)
	if not config:
		frappe.throw(_("This Veterinary administration resource is not available."), frappe.PermissionError)
	if not frappe.db.exists("DocType", config["doctype"]):
		frappe.throw(_("{0} is not installed on this site.").format(config["doctype"]))
	resolved = {"key": key, **config}
	_require_admin(resolved)
	return resolved


def _parse_object(value: str | dict | None) -> dict[str, Any]:
	if not value:
		return {}
	if isinstance(value, dict):
		return value
	parsed = frappe.parse_json(value)
	if not isinstance(parsed, dict):
		frappe.throw(_("Expected a JSON object."), frappe.ValidationError)
	return parsed


def _field_payload(meta, fieldname: str) -> dict[str, Any] | None:
	field = meta.get_field(fieldname)
	if not field:
		return None
	return {
		"fieldname": fieldname,
		"label": field.label or fieldname.replace("_", " ").title(),
		"fieldtype": field.fieldtype,
		"options": field.options or "",
		"description": field.description or "",
		"reqd": cint(field.reqd),
		"read_only": cint(field.read_only),
	}


def _columns(config: dict[str, Any]) -> list[dict[str, Any]]:
	meta = frappe.get_meta(config["doctype"])
	columns: list[dict[str, Any]] = []
	for fieldname in config.get("list_fields") or []:
		if fieldname == "name":
			columns.append({"fieldname": "name", "label": _("ID"), "fieldtype": "Data"})
		elif fieldname == "modified":
			columns.append({"fieldname": "modified", "label": _("Modified"), "fieldtype": "Datetime"})
		else:
			field = _field_payload(meta, fieldname)
			if field:
				columns.append(field)
	return columns


def _filter_schema(config: dict[str, Any]) -> list[dict[str, Any]]:
	meta = frappe.get_meta(config["doctype"])
	result = []
	for fieldname in config.get("filter_fields") or []:
		field = _field_payload(meta, fieldname)
		if field:
			field["reqd"] = 0
			field["read_only"] = 0
			result.append(field)
	return result


def _form_schema(config: dict[str, Any]) -> dict[str, Any]:
	meta = frappe.get_meta(config["doctype"])
	fields = []
	for fieldname in config.get("editor_fields") or []:
		field = _field_payload(meta, fieldname)
		if field:
			fields.append(field)
	return {
		"tabs": [
			{
				"key": "details",
				"label": _("Details"),
				"description": config["subtitle"],
				"sections": [
					{"key": "details", "label": "", "description": "", "columns": 2, "fields": fields}
				],
			}
		]
	}


def _permissions(config: dict[str, Any], doc=None) -> dict[str, bool]:
	doctype = config["doctype"]
	mode = config["mode"]
	read = bool(doc.has_permission("read") if doc else frappe.has_permission(doctype, "read"))
	if mode in {"readonly", "single_readonly"}:
		return {"read": read, "create": False, "write": False, "delete": False}
	return {
		"read": read,
		"create": bool(frappe.has_permission(doctype, "create")),
		"write": bool(doc.has_permission("write") if doc else frappe.has_permission(doctype, "write")),
		"delete": bool(doc.has_permission("delete") if doc else frappe.has_permission(doctype, "delete")),
	}


def _permission_count(doctype: str, filters: dict, or_filters: list | None = None) -> int:
	rows = frappe.get_list(
		doctype,
		fields=[{"COUNT": "*", "as": "total"}],
		filters=filters,
		or_filters=or_filters,
		limit_page_length=1,
	)
	return cint(rows[0].get("total")) if rows else 0


def _list_query(config: dict[str, Any], search: str, filters: dict[str, Any]) -> tuple[dict, list | None]:
	meta = frappe.get_meta(config["doctype"])
	query_filters: dict[str, Any] = {}
	for fieldname, value in filters.items():
		if fieldname not in set(config.get("filter_fields") or []) or value in (None, ""):
			continue
		field = meta.get_field(fieldname)
		query_filters[fieldname] = cint(value) if field and field.fieldtype == "Check" else value

	text = cstr(search).strip()
	or_filters = None
	if text:
		or_filters = [
			[config["doctype"], fieldname, "like", f"%{text}%"]
			for fieldname in config.get("search_fields") or ["name"]
			if fieldname == "name" or meta.has_field(fieldname)
		]
	return query_filters, or_filters


def _detail_values(config: dict[str, Any], doc) -> list[dict[str, Any]]:
	meta = frappe.get_meta(config["doctype"])
	result = []
	for fieldname in config.get("detail_fields") or config.get("editor_fields") or []:
		field = _field_payload(meta, fieldname)
		if not field:
			continue
		value = doc.get(fieldname)
		if field["fieldtype"] == "Check":
			value = cint(value)
		result.append({**field, "value": value})
	return result


def _document_payload(config: dict[str, Any], doc, *, is_new: bool = False) -> dict[str, Any]:
	payload = {
		"resource": config["key"],
		"doctype": config["doctype"],
		"name": None if is_new else doc.name,
		"is_new": is_new,
		"mode": config["mode"],
		"title": config["singular"] if is_new else (doc.get(frappe.get_meta(config["doctype"]).title_field) or doc.name),
		"permissions": _permissions(config, None if is_new else doc),
		"modified": None if is_new else doc.modified,
	}
	if config["mode"] in {"editable", "role_bundle"}:
		schema = _form_schema(config)
		payload["schema"] = schema
		payload["values"] = {
			field["fieldname"]: doc.get(field["fieldname"])
			for tab in schema["tabs"]
			for section in tab["sections"]
			for field in section["fields"]
		}
		if config["mode"] == "role_bundle":
			payload["roles"] = [row.role for row in (doc.get("roles") or []) if row.role]
	else:
		payload["details"] = _detail_values(config, doc)
	return payload


@frappe.whitelist()
@frappe.read_only()
def get_administration_page(
	resource: str,
	search: str = "",
	filters: str | dict | None = None,
	start: int = 0,
	page_length: int = 25,
) -> dict[str, Any]:
	config = _resource(resource)
	if not frappe.has_permission(config["doctype"], "read"):
		frappe.throw(_("You are not permitted to view {0}.").format(config["title"]), frappe.PermissionError)

	if config["mode"] == "single_readonly":
		return {
			"resource": config["key"],
			"title": config["title"],
			"singular": config["singular"],
			"subtitle": config["subtitle"],
			"mode": config["mode"],
			"columns": [{"fieldname": "name", "label": _("Profile"), "fieldtype": "Data"}],
			"filters": [],
			"rows": [{"name": config["doctype"]}],
			"total": 1,
			"start": 0,
			"page_length": 1,
			"permissions": _permissions(config),
		}

	start = max(cint(start), 0)
	page_length = min(max(cint(page_length) or 25, 1), PAGE_LENGTH_MAX)
	query_filters, or_filters = _list_query(config, search, _parse_object(filters))
	meta = frappe.get_meta(config["doctype"])
	fields = [
		fieldname
		for fieldname in config.get("list_fields") or ["name"]
		if fieldname in {"name", "modified"} or meta.has_field(fieldname)
	]
	rows = frappe.get_list(
		config["doctype"],
		fields=fields,
		filters=query_filters,
		or_filters=or_filters,
		order_by=f"{meta.sort_field or 'modified'} {meta.sort_order or 'DESC'}",
		start=start,
		page_length=page_length,
	)
	return {
		"resource": config["key"],
		"title": config["title"],
		"singular": config["singular"],
		"subtitle": config["subtitle"],
		"mode": config["mode"],
		"columns": _columns(config),
		"filters": _filter_schema(config),
		"rows": rows,
		"total": _permission_count(config["doctype"], query_filters, or_filters),
		"start": start,
		"page_length": page_length,
		"permissions": _permissions(config),
	}


@frappe.whitelist()
@frappe.read_only()
def get_administration_document(resource: str, name: str | None = None) -> dict[str, Any]:
	config = _resource(resource)
	if config["mode"] == "single_readonly":
		doc = frappe.get_single(config["doctype"])
		doc.check_permission("read")
		return _document_payload(config, doc)

	if name:
		doc = frappe.get_doc(config["doctype"], name)
		doc.check_permission("read")
		return _document_payload(config, doc)

	if config["mode"] not in {"editable", "role_bundle"}:
		frappe.throw(_("This administration resource is read-only."), frappe.PermissionError)
	if not frappe.has_permission(config["doctype"], "create"):
		frappe.throw(_("You are not permitted to create {0}.").format(config["singular"]), frappe.PermissionError)
	return _document_payload(config, frappe.new_doc(config["doctype"]), is_new=True)


def _validate_editable_values(config: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
	allowed = set(config.get("editor_fields") or [])
	payload = {key: value for key, value in values.items() if key in allowed}
	meta = frappe.get_meta(config["doctype"])
	for fieldname in allowed:
		field = meta.get_field(fieldname)
		if not field:
			continue
		if field.reqd and payload.get(fieldname) in (None, ""):
			frappe.throw(_("{0} is required.").format(field.label or fieldname), frappe.ValidationError)
		if field.fieldtype == "Check":
			payload[fieldname] = cint(payload.get(fieldname))
	return payload


def _validate_roles(roles: str | list | None) -> list[str]:
	value = frappe.parse_json(roles) if isinstance(roles, str) else (roles or [])
	if not isinstance(value, list):
		frappe.throw(_("Roles must be supplied as a list."), frappe.ValidationError)
	cleaned = []
	for role in value:
		role = cstr(role).strip()
		if not role or role in cleaned:
			continue
		if not frappe.db.exists("Role", role):
			frappe.throw(_("Role {0} does not exist.").format(role), frappe.ValidationError)
		cleaned.append(role)
	if not cleaned:
		frappe.throw(_("At least one Role is required in a Veterinary Role Bundle."), frappe.ValidationError)
	return cleaned


@frappe.whitelist()
def save_administration_document(
	resource: str,
	values: str | dict,
	name: str | None = None,
	modified: str | None = None,
	roles: str | list | None = None,
) -> dict[str, Any]:
	config = _resource(resource)
	if config["mode"] not in {"editable", "role_bundle"}:
		frappe.throw(_("This administration resource is read-only."), frappe.PermissionError)
	require_vetedge_platform_access(
		action="save_veterinary_administration",
		reference_doctype=config["doctype"],
		reference_name=name,
	)
	payload = _validate_editable_values(config, _parse_object(values))

	if name:
		doc = frappe.get_doc(config["doctype"], name)
		doc.check_permission("write")
		if modified and cstr(doc.modified) != cstr(modified):
			frappe.throw(_("This administration record changed after you opened it. Reload before saving."), frappe.TimestampMismatchError)
	else:
		if not frappe.has_permission(config["doctype"], "create"):
			frappe.throw(_("You are not permitted to create {0}.").format(config["singular"]), frappe.PermissionError)
		doc = frappe.new_doc(config["doctype"])

	for fieldname, value in payload.items():
		doc.set(fieldname, value)
	if config["mode"] == "role_bundle":
		doc.set("roles", [])
		for role in _validate_roles(roles):
			doc.append("roles", {"role": role})

	if doc.is_new():
		doc.insert()
	else:
		doc.save()
	return _document_payload(config, doc)


@frappe.whitelist()
def delete_administration_document(resource: str, name: str) -> dict[str, Any]:
	config = _resource(resource)
	if config["mode"] not in {"editable", "role_bundle"}:
		frappe.throw(_("This administration resource is read-only."), frappe.PermissionError)
	require_vetedge_platform_access(
		action="delete_veterinary_administration",
		reference_doctype=config["doctype"],
		reference_name=name,
	)
	doc = frappe.get_doc(config["doctype"], name)
	doc.check_permission("delete")
	frappe.delete_doc(config["doctype"], name)
	return {"deleted": True, "name": name}


@frappe.whitelist()
@frappe.read_only()
def search_administration_link(resource: str, fieldname: str, query: str = "", page_length: int = 20) -> list[dict[str, Any]]:
	config = _resource(resource)
	if config["mode"] != "role_bundle" or cstr(fieldname).strip() != "role":
		return []
	if not frappe.has_permission("Role", "read"):
		return []
	query = cstr(query).strip()
	filters = {"disabled": 0} if frappe.get_meta("Role").has_field("disabled") else {}
	or_filters = [["Role", "name", "like", f"%{query}%"]] if query else None
	rows = frappe.get_list(
		"Role",
		fields=["name"],
		filters=filters,
		or_filters=or_filters,
		order_by="name asc",
		page_length=min(max(cint(page_length) or 20, 1), 50),
	)
	return [{"value": row.name, "label": row.name, "description": ""} for row in rows]
