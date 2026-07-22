from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.model.workflow import get_transitions
from frappe.utils import cint

from vetedge.coreedge_adapter import get_current_vetedge_branch
from vetedge.services.platform_access import require_vetedge_platform_access
from vetedge.services.portal_access import require_internal_user

PAGE_LENGTH_MAX = 100
LAYOUT_FIELDTYPES = {"Tab Break", "Section Break", "Column Break"}
SYSTEM_FIELDS = {
	"name",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"docstatus",
	"idx",
	"parent",
	"parentfield",
	"parenttype",
	"amended_from",
}

RESOURCE_CONFIG: dict[str, dict[str, Any]] = {
	"patients": {
		"doctype": "Veterinary Patient",
		"title": _("Patients"),
		"singular": _("Patient"),
		"subtitle": _("Register and maintain complete veterinary patient records."),
		"icon": "students",
		"list_fields": [
			"name",
			"patient_name",
			"primary_owner",
			"species",
			"breed",
			"default_branch",
			"status",
			"modified",
		],
		"search_fields": ["name", "patient_name", "primary_owner", "species", "breed", "microchip_id"],
		"filter_fields": ["status", "default_branch", "species", "breed", "primary_owner"],
		"branch_field": "default_branch",
		"allow_create": True,
		"allow_delete": True,
	},
	"appointments": {
		"doctype": "Veterinary Appointment",
		"title": _("Appointments"),
		"singular": _("Appointment"),
		"subtitle": _("Schedule appointments and run the complete appointment workflow."),
		"icon": "calendar",
		"list_fields": [
			"name",
			"patient",
			"appointment_datetime",
			"practitioner_name",
			"branch",
			"appointment_type",
			"status",
		],
		"search_fields": ["name", "appointment_title", "patient", "primary_owner", "practitioner_name"],
		"filter_fields": ["status", "branch", "practitioner", "appointment_type", "patient"],
		"branch_field": "branch",
		"allow_create": True,
		"allow_delete": True,
	},
	"settings": {
		"doctype": "Veterinary Settings",
		"title": _("Veterinary Settings"),
		"singular": _("Veterinary Settings"),
		"subtitle": _("Configure clinical, operational, billing, notification, portal, and administrative controls."),
		"icon": "settings",
		"is_single": True,
		"allow_create": False,
		"allow_delete": False,
	},
}


def _require_resource(resource: str) -> dict[str, Any]:
	require_internal_user()
	key = str(resource or "").strip().lower()
	config = RESOURCE_CONFIG.get(key)
	if not config:
		frappe.throw(_("This Veterinary document workspace is not available."), frappe.PermissionError)
	if not frappe.db.exists("DocType", config["doctype"]):
		frappe.throw(_("{0} is not installed on this site.").format(config["doctype"]))
	return {"key": key, **config}


def _parse_json_object(value: str | dict | None) -> dict:
	if not value:
		return {}
	if isinstance(value, dict):
		return value
	parsed = frappe.parse_json(value)
	if not isinstance(parsed, dict):
		frappe.throw(_("Expected a JSON object."), frappe.ValidationError)
	return parsed


def _parse_json_list(value: str | list | None) -> list:
	if not value:
		return []
	if isinstance(value, list):
		return value
	parsed = frappe.parse_json(value)
	if not isinstance(parsed, list):
		frappe.throw(_("Expected a JSON list."), frappe.ValidationError)
	return parsed


def _field_label(field) -> str:
	return field.label or field.fieldname.replace("_", " ").title()


def _serialize_field(field, *, child: bool = False) -> dict[str, Any]:
	payload = {
		"fieldname": field.fieldname,
		"fieldtype": field.fieldtype,
		"label": _field_label(field),
		"options": field.options or "",
		"description": field.description or "",
		"default": field.default,
		"reqd": cint(field.reqd),
		"read_only": cint(field.read_only),
		"hidden": cint(field.hidden),
		"depends_on": field.depends_on or "",
		"mandatory_depends_on": field.mandatory_depends_on or "",
		"read_only_depends_on": field.read_only_depends_on or "",
		"in_list_view": cint(field.in_list_view),
	}
	if child:
		payload["columns"] = cint(getattr(field, "columns", 0))
	return payload


def _child_fields(options: str) -> list[dict[str, Any]]:
	if not options or not frappe.db.exists("DocType", options):
		return []
	meta = frappe.get_meta(options)
	fields = []
	for field in meta.fields:
		if not field.fieldname or field.fieldname in SYSTEM_FIELDS or field.fieldtype in LAYOUT_FIELDTYPES:
			continue
		if field.hidden and not field.depends_on:
			continue
		fields.append(_serialize_field(field, child=True))
	return fields


def _build_form_schema(meta) -> dict[str, Any]:
	tabs: list[dict[str, Any]] = []
	current_tab: dict[str, Any] | None = None
	current_section: dict[str, Any] | None = None

	def ensure_tab() -> dict[str, Any]:
		nonlocal current_tab
		if current_tab is None:
			current_tab = {"key": "general", "label": _("General"), "sections": []}
			tabs.append(current_tab)
		return current_tab

	def ensure_section() -> dict[str, Any]:
		nonlocal current_section
		tab = ensure_tab()
		if current_section is None:
			current_section = {
				"key": f"section-{len(tab['sections']) + 1}",
				"label": "",
				"description": "",
				"columns": 1,
				"fields": [],
			}
			tab["sections"].append(current_section)
		return current_section

	for field in meta.fields:
		if not field.fieldname:
			continue
		if field.fieldtype == "Tab Break":
			current_tab = {
				"key": field.fieldname,
				"label": _field_label(field),
				"description": field.description or "",
				"sections": [],
			}
			tabs.append(current_tab)
			current_section = None
			continue
		if field.fieldtype == "Section Break":
			tab = ensure_tab()
			current_section = {
				"key": field.fieldname,
				"label": _field_label(field),
				"description": field.description or "",
				"depends_on": field.depends_on or "",
				"collapsible": cint(getattr(field, "collapsible", 0)),
				"columns": 1,
				"fields": [],
			}
			tab["sections"].append(current_section)
			continue
		if field.fieldtype == "Column Break":
			section = ensure_section()
			section["columns"] = min(3, cint(section.get("columns")) + 1)
			continue
		if field.fieldname in SYSTEM_FIELDS:
			continue
		if field.hidden and not field.depends_on:
			continue
		serialized = _serialize_field(field)
		if field.fieldtype == "Table":
			serialized["child_fields"] = _child_fields(field.options)
		ensure_section()["fields"].append(serialized)

	return {
		"tabs": [
			{**tab, "sections": [section for section in tab["sections"] if section["fields"]]}
			for tab in tabs
			if any(section["fields"] for section in tab["sections"])
		],
	}


def _column_schema(meta, fieldnames: list[str]) -> list[dict[str, Any]]:
	columns = []
	for fieldname in fieldnames:
		if fieldname == "name":
			columns.append({"fieldname": "name", "label": _("ID"), "fieldtype": "Data"})
			continue
		if fieldname == "modified":
			columns.append({"fieldname": "modified", "label": _("Modified"), "fieldtype": "Datetime"})
			continue
		if fieldname == "docstatus":
			columns.append({"fieldname": "docstatus", "label": _("Document Status"), "fieldtype": "Int", "status": True})
			continue
		field = meta.get_field(fieldname)
		if not field:
			continue
		columns.append(
			{
				"fieldname": fieldname,
				"label": _field_label(field),
				"fieldtype": field.fieldtype,
				"status": fieldname in {"status", "workflow_state"},
			}
		)
	return columns


def _filter_schema(meta, fieldnames: list[str]) -> list[dict[str, Any]]:
	fields = []
	for fieldname in fieldnames:
		field = meta.get_field(fieldname)
		if not field:
			continue
		serialized = _serialize_field(field)
		serialized["reqd"] = 0
		serialized["read_only"] = 0
		fields.append(serialized)
	return fields


def _branch_filters(config: dict[str, Any], meta) -> dict[str, Any]:
	fieldname = config.get("branch_field")
	if not fieldname or not meta.has_field(fieldname):
		return {}
	try:
		branch = get_current_vetedge_branch()
	except Exception:
		branch = None
	if branch and str(branch).strip().lower() not in {"all", "all branches"}:
		return {fieldname: branch}
	return {}


def _permission_count(doctype: str, filters: dict, or_filters: list | None) -> int:
	rows = frappe.get_list(
		doctype,
		fields=[{"COUNT": "*", "as": "total"}],
		filters=filters,
		or_filters=or_filters,
		limit_page_length=1,
	)
	return cint(rows[0].get("total")) if rows else 0


def _document_values(doc, schema: dict[str, Any]) -> dict[str, Any]:
	values: dict[str, Any] = {}
	for tab in schema.get("tabs") or []:
		for section in tab.get("sections") or []:
			for field in section.get("fields") or []:
				fieldname = field["fieldname"]
				if field["fieldtype"] == "Password":
					values[fieldname] = ""
					field["has_value"] = bool(doc.get(fieldname))
					continue
				value = doc.get(fieldname)
				if field["fieldtype"] == "Table":
					values[fieldname] = [row.as_dict(no_nulls=False) for row in value or []]
				else:
					values[fieldname] = value
	return values


def _workflow_transitions(doc) -> list[dict[str, Any]]:
	try:
		transitions = get_transitions(doc)
	except Exception:
		return []
	return [
		{
			"action": transition.get("action"),
			"label": transition.get("action"),
			"next_state": transition.get("next_state"),
			"primary": True,
		}
		for transition in transitions
		if transition.get("action")
	]


def _appointment_actions(doc) -> list[dict[str, Any]]:
	actions: list[dict[str, Any]] = []
	if doc.guest_booking_request:
		actions.append(
			{
				"key": "open-registration-request",
				"label": _("Open Registration Request"),
				"kind": "navigate",
				"route": f"/app/veterinary-guest-booking-request/{doc.guest_booking_request}",
			}
		)
	if doc.linked_consultation:
		actions.append(
			{
				"key": "open-service-consultation",
				"label": _("Open Service Consultation"),
				"kind": "navigate",
				"route": f"/app/veterinary-consultation/{doc.linked_consultation}",
			}
		)
	if doc.follow_up_reference:
		actions.append(
			{
				"key": "open-originating-consultation",
				"label": _("Open Originating Consultation"),
				"kind": "navigate",
				"route": f"/app/veterinary-consultation/{doc.follow_up_reference}",
			}
		)
	if doc.linked_consultation:
		return actions
	if doc.status == "Owner Requested":
		actions.extend(
			[
				{"key": "approve-appointment", "label": _("Approve Appointment"), "kind": "appointment_status", "status": "Scheduled", "primary": True},
				{"key": "cancel-request", "label": _("Cancel Request"), "kind": "appointment_status", "status": "Cancelled", "danger": True, "confirm": _("Cancel this appointment request?")},
			]
		)
	elif doc.status == "Scheduled":
		actions.append(
			{"key": "confirm-appointment", "label": _("Confirm Appointment"), "kind": "appointment_status", "status": "Confirmed", "primary": True}
		)
	elif doc.status == "Confirmed":
		actions.extend(
			[
				{"key": "check-in", "label": _("Check In"), "kind": "appointment_status", "status": "Checked In", "primary": True},
				{"key": "start-consultation", "label": _("Start Consultation"), "kind": "start_consultation", "primary": True},
			]
		)
	elif doc.status == "Checked In":
		actions.append(
			{"key": "start-consultation", "label": _("Start Consultation"), "kind": "start_consultation", "primary": True}
		)
	return actions


def _custom_actions(config: dict[str, Any], doc) -> list[dict[str, Any]]:
	if config["key"] == "appointments":
		return _appointment_actions(doc)
	if config["key"] == "patients" and not doc.is_new():
		return [
			{
				"key": "new-appointment",
				"label": _("New Appointment"),
				"kind": "navigate",
				"route": f"/app/vetedge-document-workspace?resource=appointments&new=1&patient={doc.name}",
				"primary": True,
			}
		]
	return []


def _permissions(config: dict[str, Any], doc=None) -> dict[str, bool]:
	doctype = config["doctype"]
	if doc is None:
		return {
			"read": bool(frappe.has_permission(doctype, "read")),
			"create": bool(config.get("allow_create") and frappe.has_permission(doctype, "create")),
			"write": bool(frappe.has_permission(doctype, "write")),
			"delete": bool(config.get("allow_delete") and frappe.has_permission(doctype, "delete")),
		}
	return {
		"read": bool(doc.has_permission("read")),
		"create": bool(config.get("allow_create") and frappe.has_permission(doctype, "create")),
		"write": bool(doc.has_permission("write")),
		"delete": bool(config.get("allow_delete") and doc.has_permission("delete")),
	}


@frappe.whitelist()
def get_resource_definition(resource: str) -> dict[str, Any]:
	config = _require_resource(resource)
	meta = frappe.get_meta(config["doctype"])
	permissions = _permissions(config)
	if not permissions["read"]:
		frappe.throw(_("You are not permitted to view {0}.").format(config["doctype"]), frappe.PermissionError)
	return {
		"resource": config["key"],
		"doctype": config["doctype"],
		"title": config["title"],
		"singular": config["singular"],
		"subtitle": config["subtitle"],
		"icon": config["icon"],
		"is_single": bool(config.get("is_single")),
		"permissions": permissions,
		"columns": _column_schema(meta, config.get("list_fields") or []),
		"filters": _filter_schema(meta, config.get("filter_fields") or []),
	}


@frappe.whitelist()
def get_document_list(
	resource: str,
	search: str = "",
	filters: str | dict | None = None,
	start: int = 0,
	page_length: int = 25,
) -> dict[str, Any]:
	config = _require_resource(resource)
	if config.get("is_single"):
		frappe.throw(_("This resource is a single settings document."), frappe.ValidationError)
	doctype = config["doctype"]
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("You are not permitted to view {0}.").format(doctype), frappe.PermissionError)
	meta = frappe.get_meta(doctype)
	query_filters = _branch_filters(config, meta)
	allowed_filters = set(config.get("filter_fields") or [])
	for fieldname, value in _parse_json_object(filters).items():
		if fieldname in allowed_filters and value not in (None, "", []):
			query_filters[fieldname] = value
	query = str(search or "").strip()
	or_filters = None
	if query:
		or_filters = [[doctype, fieldname, "like", f"%{query}%"] for fieldname in config.get("search_fields") or ["name"]]
	start = max(cint(start), 0)
	page_length = min(max(cint(page_length) or 25, 1), PAGE_LENGTH_MAX)
	fields = [fieldname for fieldname in config.get("list_fields") or ["name"] if fieldname == "name" or meta.has_field(fieldname)]
	rows = frappe.get_list(
		doctype,
		fields=fields,
		filters=query_filters,
		or_filters=or_filters,
		order_by=f"{meta.sort_field or 'modified'} {meta.sort_order or 'DESC'}",
		start=start,
		page_length=page_length,
	)
	return {
		"rows": rows,
		"total": _permission_count(doctype, query_filters, or_filters),
		"start": start,
		"page_length": page_length,
	}


@frappe.whitelist()
def get_document(resource: str, name: str | None = None, defaults: str | dict | None = None) -> dict[str, Any]:
	config = _require_resource(resource)
	doctype = config["doctype"]
	meta = frappe.get_meta(doctype)
	is_new = not name and not config.get("is_single")
	if config.get("is_single"):
		doc = frappe.get_single(doctype)
		doc.check_permission("read")
	elif name:
		doc = frappe.get_doc(doctype, name)
		doc.check_permission("read")
	else:
		if not config.get("allow_create") or not frappe.has_permission(doctype, "create"):
			frappe.throw(_("You are not permitted to create {0}.").format(doctype), frappe.PermissionError)
		doc = frappe.new_doc(doctype)
		for fieldname, value in _parse_json_object(defaults).items():
			if meta.has_field(fieldname):
				doc.set(fieldname, value)
		branch_field = config.get("branch_field")
		if branch_field and meta.has_field(branch_field) and not doc.get(branch_field):
			doc.set(branch_field, get_current_vetedge_branch())
	schema = _build_form_schema(meta)
	permissions = _permissions(config, doc)
	state_field = meta.workflow_state_field or ("status" if meta.has_field("status") else "")
	return {
		"resource": config["key"],
		"doctype": doctype,
		"name": None if is_new else doc.name,
		"is_new": is_new,
		"is_single": bool(config.get("is_single")),
		"title": config["singular"] if is_new else (doc.get(meta.title_field) if meta.title_field else doc.name),
		"schema": schema,
		"values": _document_values(doc, schema),
		"docstatus": cint(doc.docstatus),
		"state_field": state_field,
		"state": doc.get(state_field) if state_field else "",
		"permissions": permissions,
		"workflow_transitions": _workflow_transitions(doc) if not is_new else [],
		"actions": _custom_actions(config, doc),
		"modified": doc.modified if not is_new else None,
	}


def _writable_fieldnames(meta) -> set[str]:
	return {
		field.fieldname
		for field in meta.fields
		if field.fieldname
		and field.fieldname not in SYSTEM_FIELDS
		and field.fieldtype not in LAYOUT_FIELDTYPES
		and not field.read_only
		and not getattr(field, "virtual", False)
	}


def _apply_values(doc, meta, values: dict[str, Any]) -> None:
	allowed = _writable_fieldnames(meta)
	for fieldname, value in values.items():
		if fieldname not in allowed:
			continue
		field = meta.get_field(fieldname)
		if field.fieldtype == "Password" and value in (None, "", "********"):
			continue
		if field.fieldtype == "Table":
			rows = value if isinstance(value, list) else []
			doc.set(fieldname, [])
			child_meta = frappe.get_meta(field.options)
			child_allowed = _writable_fieldnames(child_meta)
			for row in rows:
				if not isinstance(row, dict):
					continue
				payload = {key: item for key, item in row.items() if key in child_allowed or key == "name"}
				doc.append(fieldname, payload)
			continue
		doc.set(fieldname, value)


@frappe.whitelist()
def save_document(
	resource: str,
	values: str | dict,
	name: str | None = None,
	modified: str | None = None,
) -> dict[str, Any]:
	config = _require_resource(resource)
	doctype = config["doctype"]
	require_vetedge_platform_access(
		action="save_document_workspace",
		reference_doctype=doctype,
		reference_name=name,
	)
	meta = frappe.get_meta(doctype)
	if config.get("is_single"):
		doc = frappe.get_single(doctype)
		doc.check_permission("write")
	elif name:
		doc = frappe.get_doc(doctype, name)
		doc.check_permission("write")
		if modified and str(doc.modified) != str(modified):
			frappe.throw(
				_("This document changed after you opened it. Reload before saving."),
				frappe.TimestampMismatchError,
			)
	else:
		if not config.get("allow_create") or not frappe.has_permission(doctype, "create"):
			frappe.throw(_("You are not permitted to create {0}.").format(doctype), frappe.PermissionError)
		doc = frappe.new_doc(doctype)
	_apply_values(doc, meta, _parse_json_object(values))
	if doc.is_new():
		doc.insert()
	else:
		doc.save()
	return get_document(config["key"], None if config.get("is_single") else doc.name)


@frappe.whitelist()
def delete_document(resource: str, name: str) -> dict[str, Any]:
	config = _require_resource(resource)
	if config.get("is_single") or not config.get("allow_delete"):
		frappe.throw(_("Deletion is not available for this resource."), frappe.PermissionError)
	doc = frappe.get_doc(config["doctype"], name)
	doc.check_permission("delete")
	if cint(doc.docstatus) != 0:
		frappe.throw(_("Submitted documents cannot be deleted."), frappe.ValidationError)
	require_vetedge_platform_access(
		action="delete_document_workspace",
		reference_doctype=config["doctype"],
		reference_name=name,
	)
	frappe.delete_doc(config["doctype"], name)
	return {"deleted": True, "name": name}


@frappe.whitelist()
def get_link_options(
	resource: str,
	fieldname: str,
	query: str = "",
	values: str | dict | None = None,
	child_doctype: str | None = None,
	page_length: int = 20,
) -> list[dict[str, Any]]:
	config = _require_resource(resource)
	parent_meta = frappe.get_meta(child_doctype) if child_doctype else frappe.get_meta(config["doctype"])
	field = parent_meta.get_field(fieldname)
	if not field or field.fieldtype not in {"Link", "Dynamic Link"}:
		frappe.throw(_("This field does not support record lookup."), frappe.ValidationError)
	context = _parse_json_object(values)
	options = field.options
	if field.fieldtype == "Dynamic Link":
		options = context.get(field.options)
	if not options or not frappe.db.exists("DocType", options):
		return []
	page_length = min(max(cint(page_length) or 20, 1), 50)
	text = str(query or "").strip()

	if config["key"] == "appointments" and fieldname == "practitioner":
		from vetedge.services.permissions import get_veterinary_doctor_users

		rows = get_veterinary_doctor_users(options, text, "name", 0, page_length, {})
		return [{"value": row[0], "label": row[1] or row[0]} for row in rows]

	filters: dict[str, Any] = {}
	if config["key"] == "appointments" and fieldname == "patient":
		filters["status"] = ["!=", "Deceased"]
	if config["key"] == "patients" and fieldname == "breed" and context.get("species"):
		option_meta = frappe.get_meta(options)
		if option_meta.has_field("species"):
			filters["species"] = context["species"]

	option_meta = frappe.get_meta(options)
	title_field = option_meta.title_field if option_meta.title_field and option_meta.has_field(option_meta.title_field) else "name"
	fields = ["name"]
	if title_field != "name":
		fields.append(title_field)
	search_fields = ["name"]
	for candidate in (title_field, *(str(option_meta.search_fields or "").split(","))):
		candidate = str(candidate or "").strip()
		if candidate and option_meta.has_field(candidate) and candidate not in search_fields:
			search_fields.append(candidate)
	or_filters = [[options, candidate, "like", f"%{text}%"] for candidate in search_fields[:5]] if text else None
	rows = frappe.get_list(
		options,
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


@frappe.whitelist()
def apply_workflow_transition(resource: str, name: str, action: str) -> dict[str, Any]:
	config = _require_resource(resource)
	require_vetedge_platform_access(
		action="apply_document_workflow",
		reference_doctype=config["doctype"],
		reference_name=name,
	)
	from frappe.model.workflow import apply_workflow

	doc = frappe.get_doc(config["doctype"], name)
	doc.check_permission("read")
	apply_workflow(doc.as_dict(), action)
	return get_document(config["key"], name)


@frappe.whitelist()
def perform_document_action(resource: str, name: str, action: str | dict) -> dict[str, Any]:
	config = _require_resource(resource)
	payload = _parse_json_object(action)
	kind = payload.get("kind")
	if kind == "navigate":
		return {"route": payload.get("route"), "refresh": False}
	if config["key"] != "appointments":
		frappe.throw(_("This document action is not supported."), frappe.ValidationError)
	if kind == "appointment_status":
		from vetedge.services.appointment_flow import transition_appointment_status

		result = transition_appointment_status(name, payload.get("status"))
		return {"result": result, "document": get_document(config["key"], name), "refresh": True}
	if kind == "start_consultation":
		from vetedge.services.appointment_flow import create_consultation_from_appointment

		result = create_consultation_from_appointment(name)
		return {
			"result": result,
			"document": get_document(config["key"], name),
			"route": f"/app/veterinary-consultation/{result.get('name')}",
			"refresh": True,
		}
	frappe.throw(_("This appointment action is not supported."), frappe.ValidationError)
