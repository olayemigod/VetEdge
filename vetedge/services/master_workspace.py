from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

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

MASTER_CONFIG: dict[str, dict[str, Any]] = {
	"species": {
		"doctype": "Veterinary Species",
		"title": _("Species"),
		"singular": _("Species"),
		"subtitle": _("Maintain the animal species available throughout Veterinary workflows."),
		"icon": "sprout",
		"list_fields": ["name", "species_name", "description", "disabled", "modified"],
		"search_fields": ["name", "species_name", "description"],
		"filter_fields": ["disabled"],
	},
	"breeds": {
		"doctype": "Veterinary Breed",
		"title": _("Breeds"),
		"singular": _("Breed"),
		"subtitle": _("Maintain breeds and keep every breed linked to a valid active species."),
		"icon": "list",
		"list_fields": ["name", "breed_name", "species", "description", "disabled", "modified"],
		"search_fields": ["name", "breed_name", "species", "description"],
		"filter_fields": ["species", "disabled"],
		"link_filters": {"species": {"disabled": 0}},
	},
	"symptoms": {
		"doctype": "Veterinary Symptom",
		"title": _("Symptoms"),
		"singular": _("Symptom"),
		"subtitle": _("Maintain reusable symptoms grouped by body system for faster clinical entry."),
		"icon": "activity",
		"list_fields": ["name", "symptom_name", "body_system", "description", "disabled", "modified"],
		"search_fields": ["name", "symptom_name", "body_system", "description"],
		"filter_fields": ["body_system", "disabled"],
	},
	"diagnosis-categories": {
		"doctype": "Veterinary Diagnosis Category",
		"title": _("Diagnosis Categories"),
		"singular": _("Diagnosis Category"),
		"subtitle": _("Organise veterinary diagnoses into reusable clinical categories."),
		"icon": "layers",
		"list_fields": ["name", "category_name", "description", "disabled", "modified"],
		"search_fields": ["name", "category_name", "description"],
		"filter_fields": ["disabled"],
	},
	"diagnoses": {
		"doctype": "Veterinary Diagnosis",
		"title": _("Diagnoses"),
		"singular": _("Diagnosis"),
		"subtitle": _("Maintain standard diagnoses and optionally assign an active diagnosis category."),
		"icon": "clipboard",
		"list_fields": ["name", "diagnosis_name", "category", "description", "disabled", "modified"],
		"search_fields": ["name", "diagnosis_name", "category", "description"],
		"filter_fields": ["category", "disabled"],
		"link_filters": {"category": {"disabled": 0}},
	},
	"service-types": {
		"doctype": "Veterinary Service Type",
		"title": _("Service Types"),
		"singular": _("Service Type"),
		"subtitle": _("Maintain operational service categories and safe ERPNext sales-item defaults."),
		"icon": "tool",
		"list_fields": [
			"name",
			"service_type_name",
			"service_category",
			"default_item",
			"standard_rate",
			"disabled",
			"modified",
		],
		"search_fields": ["name", "service_type_name", "service_category", "default_item", "description"],
		"filter_fields": ["service_category", "default_item", "disabled"],
		"link_filters": {"default_item": {"disabled": 0, "is_sales_item": 1}},
	},
	"consultation-types": {
		"doctype": "Consultation Type",
		"title": _("Consultation Types"),
		"singular": _("Consultation Type"),
		"subtitle": _("Maintain consultation labels, house-call behaviour and display order."),
		"icon": "clipboard",
		"list_fields": [
			"name",
			"consultation_type",
			"is_house_call",
			"sort_order",
			"disabled",
			"modified",
		],
		"search_fields": ["name", "consultation_type", "description"],
		"filter_fields": ["is_house_call", "disabled"],
	},
}


def _require_master(resource: str) -> dict[str, Any]:
	require_internal_user()
	key = str(resource or "").strip().lower()
	config = MASTER_CONFIG.get(key)
	if not config:
		frappe.throw(_("This Veterinary master workspace is not available."), frappe.PermissionError)
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


def _field_label(field) -> str:
	return field.label or field.fieldname.replace("_", " ").title()


def _serialize_field(field) -> dict[str, Any]:
	return {
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


def _form_schema(meta) -> dict[str, Any]:
	fields = []
	for field in meta.fields:
		if not field.fieldname or field.fieldname in SYSTEM_FIELDS or field.fieldtype in LAYOUT_FIELDTYPES:
			continue
		if field.hidden and not field.depends_on:
			continue
		if field.fieldtype in {"Table", "Table MultiSelect", "HTML", "Button", "Image"}:
			frappe.throw(
				_("{0} cannot yet be safely managed in the Veterinary master workspace because field {1} requires a dedicated provider.").format(
					meta.name,
					_field_label(field),
				)
			)
		fields.append(_serialize_field(field))
	return {
		"tabs": [
			{
				"key": "details",
				"label": _("Details"),
				"description": _("Maintain the complete master record."),
				"sections": [
					{
						"key": "master-details",
						"label": "",
						"description": "",
						"columns": 2,
						"fields": fields,
					}
				],
			}
		]
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
		field = meta.get_field(fieldname)
		if not field:
			continue
		columns.append(
			{
				"fieldname": fieldname,
				"label": _field_label(field),
				"fieldtype": field.fieldtype,
				"status": fieldname == "disabled",
			}
		)
	return columns


def _filter_schema(meta, fieldnames: list[str]) -> list[dict[str, Any]]:
	filters = []
	for fieldname in fieldnames:
		field = meta.get_field(fieldname)
		if not field:
			continue
		payload = _serialize_field(field)
		payload["reqd"] = 0
		payload["read_only"] = 0
		filters.append(payload)
	return filters


def _permissions(config: dict[str, Any], doc=None) -> dict[str, bool]:
	doctype = config["doctype"]
	return {
		"read": bool(doc.has_permission("read") if doc else frappe.has_permission(doctype, "read")),
		"create": bool(frappe.has_permission(doctype, "create")),
		"write": bool(doc.has_permission("write") if doc else frappe.has_permission(doctype, "write")),
		"delete": bool(doc.has_permission("delete") if doc else frappe.has_permission(doctype, "delete")),
	}


def _permission_count(doctype: str, filters: dict, or_filters: list | None) -> int:
	rows = frappe.get_list(
		doctype,
		fields=[{"COUNT": "*", "as": "total"}],
		filters=filters,
		or_filters=or_filters,
		limit_page_length=1,
	)
	return cint(rows[0].get("total")) if rows else 0


def _normalize_filter(field, value):
	if value in (None, "", []):
		return None
	if field and field.fieldtype == "Check":
		return cint(value)
	return value


def _document_values(doc, schema: dict[str, Any]) -> dict[str, Any]:
	values: dict[str, Any] = {}
	for tab in schema.get("tabs") or []:
		for section in tab.get("sections") or []:
			for field in section.get("fields") or []:
				values[field["fieldname"]] = doc.get(field["fieldname"])
	return values


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


def _assert_active_link(doctype: str, name: str | None, label: str) -> None:
	if not name:
		return
	if not frappe.db.exists(doctype, name):
		frappe.throw(_("{0} {1} does not exist.").format(label, name), frappe.ValidationError)
	meta = frappe.get_meta(doctype)
	if meta.has_field("disabled") and cint(frappe.db.get_value(doctype, name, "disabled")):
		frappe.throw(_("{0} {1} is disabled and cannot be selected.").format(label, name), frappe.ValidationError)


def _validate_master_values(config: dict[str, Any], values: dict[str, Any]) -> None:
	key = config["key"]
	if key == "breeds":
		_assert_active_link("Veterinary Species", values.get("species"), _("Species"))
	elif key == "diagnoses":
		_assert_active_link("Veterinary Diagnosis Category", values.get("category"), _("Diagnosis Category"))
	elif key == "service-types":
		item = values.get("default_item")
		if item:
			row = frappe.db.get_value("Item", item, ["disabled", "is_sales_item"], as_dict=True)
			if not row:
				frappe.throw(_("ERPNext Item {0} does not exist.").format(item), frappe.ValidationError)
			if cint(row.disabled) or not cint(row.is_sales_item):
				frappe.throw(
					_("Default ERPNext Item must be an enabled sales item."),
					frappe.ValidationError,
				)
		if values.get("standard_rate") not in (None, "") and flt(values.get("standard_rate")) < 0:
			frappe.throw(_("Standard Rate cannot be negative."), frappe.ValidationError)
	elif key == "consultation-types":
		if values.get("sort_order") not in (None, "") and cint(values.get("sort_order")) < 0:
			frappe.throw(_("Sort Order cannot be negative."), frappe.ValidationError)


def _apply_values(doc, meta, values: dict[str, Any]) -> None:
	allowed = _writable_fieldnames(meta)
	for fieldname, value in values.items():
		if fieldname not in allowed:
			continue
		doc.set(fieldname, value)


@frappe.whitelist()
def get_master_definition(resource: str) -> dict[str, Any]:
	config = _require_master(resource)
	doctype = config["doctype"]
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("You are not permitted to view {0}.").format(doctype), frappe.PermissionError)
	meta = frappe.get_meta(doctype)
	return {
		"resource": config["key"],
		"doctype": doctype,
		"title": config["title"],
		"singular": config["singular"],
		"subtitle": config["subtitle"],
		"icon": config["icon"],
		"permissions": _permissions(config),
		"columns": _column_schema(meta, config.get("list_fields") or ["name", "modified"]),
		"filters": _filter_schema(meta, config.get("filter_fields") or []),
	}


@frappe.whitelist()
def get_master_list(
	resource: str,
	search: str = "",
	filters: str | dict | None = None,
	start: int = 0,
	page_length: int = 25,
) -> dict[str, Any]:
	config = _require_master(resource)
	doctype = config["doctype"]
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("You are not permitted to view {0}.").format(doctype), frappe.PermissionError)
	meta = frappe.get_meta(doctype)
	query_filters: dict[str, Any] = {}
	allowed_filters = set(config.get("filter_fields") or [])
	for fieldname, value in _parse_json_object(filters).items():
		if fieldname not in allowed_filters:
			continue
		normalized = _normalize_filter(meta.get_field(fieldname), value)
		if normalized is not None:
			query_filters[fieldname] = normalized

	query = str(search or "").strip()
	or_filters = None
	if query:
		or_filters = [
			[doctype, fieldname, "like", f"%{query}%"]
			for fieldname in config.get("search_fields") or ["name"]
			if fieldname == "name" or meta.has_field(fieldname)
		]

	start = max(cint(start), 0)
	page_length = min(max(cint(page_length) or 25, 1), PAGE_LENGTH_MAX)
	fields = [
		fieldname
		for fieldname in config.get("list_fields") or ["name"]
		if fieldname in {"name", "modified"} or meta.has_field(fieldname)
	]
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
def get_master_document(resource: str, name: str | None = None) -> dict[str, Any]:
	config = _require_master(resource)
	doctype = config["doctype"]
	meta = frappe.get_meta(doctype)
	is_new = not name
	if name:
		doc = frappe.get_doc(doctype, name)
		doc.check_permission("read")
	else:
		if not frappe.has_permission(doctype, "create"):
			frappe.throw(_("You are not permitted to create {0}.").format(doctype), frappe.PermissionError)
		doc = frappe.new_doc(doctype)
	schema = _form_schema(meta)
	permissions = _permissions(config, doc if not is_new else None)
	return {
		"resource": config["key"],
		"doctype": doctype,
		"name": None if is_new else doc.name,
		"is_new": is_new,
		"title": config["singular"] if is_new else (doc.get(meta.title_field) if meta.title_field else doc.name),
		"schema": schema,
		"values": _document_values(doc, schema),
		"docstatus": cint(doc.docstatus),
		"state": _("Disabled") if cint(doc.get("disabled")) else _("Active"),
		"permissions": permissions,
		"modified": None if is_new else doc.modified,
	}


@frappe.whitelist()
def save_master_document(
	resource: str,
	values: str | dict,
	name: str | None = None,
	modified: str | None = None,
) -> dict[str, Any]:
	config = _require_master(resource)
	doctype = config["doctype"]
	require_vetedge_platform_access(
		action="save_master_workspace",
		reference_doctype=doctype,
		reference_name=name,
	)
	meta = frappe.get_meta(doctype)
	payload = _parse_json_object(values)
	_validate_master_values(config, payload)
	if name:
		doc = frappe.get_doc(doctype, name)
		doc.check_permission("write")
		if modified and str(doc.modified) != str(modified):
			frappe.throw(
				_("This master record changed after you opened it. Reload before saving."),
				frappe.TimestampMismatchError,
			)
	else:
		if not frappe.has_permission(doctype, "create"):
			frappe.throw(_("You are not permitted to create {0}.").format(doctype), frappe.PermissionError)
		doc = frappe.new_doc(doctype)
	_apply_values(doc, meta, payload)
	if doc.is_new():
		doc.insert()
	else:
		doc.save()
	return get_master_document(config["key"], doc.name)


@frappe.whitelist()
def delete_master_document(resource: str, name: str) -> dict[str, Any]:
	config = _require_master(resource)
	doctype = config["doctype"]
	require_vetedge_platform_access(
		action="delete_master_workspace",
		reference_doctype=doctype,
		reference_name=name,
	)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("delete")
	frappe.delete_doc(doctype, name)
	return {"deleted": True, "name": name}


@frappe.whitelist()
def get_master_link_options(
	resource: str,
	fieldname: str,
	query: str = "",
	page_length: int = 20,
) -> list[dict[str, Any]]:
	config = _require_master(resource)
	meta = frappe.get_meta(config["doctype"])
	field = meta.get_field(fieldname)
	if not field or field.fieldtype != "Link":
		frappe.throw(_("This field does not support record lookup."), frappe.ValidationError)
	options = field.options
	if not options or not frappe.db.exists("DocType", options):
		return []
	if not frappe.has_permission(options, "read"):
		return []

	filters = dict((config.get("link_filters") or {}).get(fieldname) or {})
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
	text = str(query or "").strip()
	or_filters = [[options, candidate, "like", f"%{text}%"] for candidate in search_fields[:5]] if text else None
	page_length = min(max(cint(page_length) or 20, 1), 50)
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
