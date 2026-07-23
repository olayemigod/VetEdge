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

PRICING_MASTER_CONFIG: dict[str, dict[str, Any]] = {
	"treatment-items": {
		"doctype": "Veterinary Treatment Item",
		"title": _("Treatment Items"),
		"singular": _("Treatment Item"),
		"subtitle": _("Curate ERPNext Items used for treatment, dispensary and consultation billing."),
		"icon": "layers",
		"identity_fields": ["item"],
		"list_fields": [
			"name",
			"item",
			"item_name",
			"service_type",
			"treatment_type",
			"default_price",
			"disabled",
			"modified",
		],
		"search_fields": ["name", "item", "item_name", "service_type", "treatment_type"],
		"filter_fields": ["service_type", "treatment_type", "price_list", "disabled"],
		"link_filters": {
			"item": {"disabled": 0, "is_sales_item": 1},
			"price_list": {"enabled": 1, "selling": 1},
			"service_type": {"disabled": 0},
			"treatment_type": {"disabled": 0},
		},
		"notice": _(
			"Saving a positive Default Price updates the linked ERPNext Item Price. A positive Shelf Life also updates the linked Item shelf-life setting."
		),
		"side_effects": ["item_price", "item_shelf_life"],
	},
	"treatment-types": {
		"doctype": "Veterinary Treatment Type",
		"title": _("Treatment Types"),
		"singular": _("Treatment Type"),
		"subtitle": _("Maintain treatment categories, dispensary requirements and default billing Items."),
		"icon": "settings",
		"identity_fields": ["treatment_type_name"],
		"list_fields": [
			"name",
			"treatment_type_name",
			"treatment_category",
			"default_item",
			"requires_dispensary",
			"disabled",
			"modified",
		],
		"search_fields": ["name", "treatment_type_name", "treatment_category", "default_item"],
		"filter_fields": ["treatment_category", "requires_dispensary", "disabled"],
		"link_filters": {"default_item": {"disabled": 0, "is_sales_item": 1}},
		"notice": _("Use Requires Dispensary Confirmation only where stock or medication release must be acknowledged."),
		"side_effects": [],
	},
	"lab-tests": {
		"doctype": "Veterinary Lab Test",
		"title": _("Lab Tests"),
		"singular": _("Lab Test"),
		"subtitle": _("Maintain test structure, result-entry rules and non-stock billing prices."),
		"icon": "assessment",
		"identity_fields": ["test_name"],
		"list_fields": [
			"name",
			"test_name",
			"test_code",
			"sample_type",
			"result_format",
			"linked_item",
			"default_rate",
			"is_active",
			"modified",
		],
		"search_fields": ["name", "test_name", "test_code", "sample_type", "linked_item"],
		"filter_fields": ["sample_type", "result_format", "linked_item", "is_active"],
		"link_filters": {
			"linked_item": {"disabled": 0, "is_sales_item": 1, "is_stock_item": 0},
			"price_list": {"enabled": 1, "selling": 1},
		},
		"notice": _(
			"Linked Billing Item must be a non-stock sales Item. Saving a positive Default Price updates its ERPNext Item Price."
		),
		"side_effects": ["item_price"],
	},
	"vaccines": {
		"doctype": "Veterinary Vaccine",
		"title": _("Vaccines"),
		"singular": _("Vaccine"),
		"subtitle": _("Maintain vaccine applicability, preventive schedules, stock Items and prices."),
		"icon": "shield",
		"identity_fields": ["vaccine_name"],
		"list_fields": [
			"name",
			"vaccine_name",
			"vaccine_code",
			"species",
			"default_item",
			"default_price",
			"is_active",
			"modified",
		],
		"search_fields": ["name", "vaccine_name", "vaccine_code", "species", "default_item"],
		"filter_fields": ["species", "default_item", "is_active"],
		"link_filters": {
			"species": {"disabled": 0},
			"default_item": {"disabled": 0, "is_sales_item": 1},
			"price_list": {"enabled": 1, "selling": 1},
		},
		"notice": _(
			"The Default Item may be stock or non-stock, but must be an enabled sales Item. Positive Default Price values update ERPNext Item Price."
		),
		"side_effects": ["item_price"],
	},
	"grooming-services": {
		"doctype": "Pet Grooming Service",
		"title": _("Grooming Services"),
		"singular": _("Grooming Service"),
		"subtitle": _("Maintain grooming duration, availability and non-stock billing defaults."),
		"icon": "activity",
		"identity_fields": ["service_name"],
		"list_fields": [
			"name",
			"service_name",
			"service_code",
			"default_item",
			"default_rate",
			"estimated_duration",
			"is_active",
			"modified",
		],
		"search_fields": ["name", "service_name", "service_code", "default_item"],
		"filter_fields": ["default_item", "is_active"],
		"link_filters": {"default_item": {"disabled": 0, "is_sales_item": 1, "is_stock_item": 0}},
		"notice": _("Grooming must be enabled in Veterinary Settings before these records can be saved."),
		"side_effects": [],
	},
}


def _require_resource(resource: str) -> dict[str, Any]:
	require_internal_user()
	key = str(resource or "").strip().lower()
	config = PRICING_MASTER_CONFIG.get(key)
	if not config:
		frappe.throw(_("This Veterinary pricing master is not available."), frappe.PermissionError)
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


def _serialize_field(field, *, read_only: bool = False) -> dict[str, Any]:
	return {
		"fieldname": field.fieldname,
		"fieldtype": field.fieldtype,
		"label": _field_label(field),
		"options": field.options or "",
		"description": field.description or "",
		"default": field.default,
		"reqd": cint(field.reqd),
		"read_only": 1 if read_only else cint(field.read_only),
		"hidden": cint(field.hidden),
		"depends_on": field.depends_on or "",
		"mandatory_depends_on": field.mandatory_depends_on or "",
		"read_only_depends_on": field.read_only_depends_on or "",
		"in_list_view": cint(field.in_list_view),
	}


def _build_form_schema(meta, config: dict[str, Any], *, is_new: bool) -> dict[str, Any]:
	tabs: list[dict[str, Any]] = []
	current_tab: dict[str, Any] | None = None
	current_section: dict[str, Any] | None = None
	identity_fields = set(config.get("identity_fields") or [])

	def ensure_tab() -> dict[str, Any]:
		nonlocal current_tab
		if current_tab is None:
			current_tab = {"key": "general", "label": _("General"), "description": "", "sections": []}
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
		if field.fieldtype in {"Table", "Table MultiSelect", "HTML", "Button", "Image"}:
			frappe.throw(
				_("{0} requires a dedicated provider because field {1} is not safe in the pricing master workspace.").format(
					meta.name,
					_field_label(field),
				)
			)
		read_only = (not is_new and field.fieldname in identity_fields) or bool(field.read_only)
		ensure_section()["fields"].append(_serialize_field(field, read_only=read_only))

	return {
		"tabs": [
			{**tab, "sections": [section for section in tab["sections"] if section["fields"]]}
			for tab in tabs
			if any(section["fields"] for section in tab["sections"])
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
				"status": fieldname in {"disabled", "is_active"},
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


def _permissions(doctype: str, doc=None) -> dict[str, bool]:
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


def _writable_fieldnames(meta, config: dict[str, Any], *, is_new: bool) -> set[str]:
	identity_fields = set(config.get("identity_fields") or [])
	return {
		field.fieldname
		for field in meta.fields
		if field.fieldname
		and field.fieldname not in SYSTEM_FIELDS
		and field.fieldtype not in LAYOUT_FIELDTYPES
		and not field.read_only
		and not getattr(field, "virtual", False)
		and (is_new or field.fieldname not in identity_fields)
	}


def _assert_active_link(doctype: str, name: str | None, label: str) -> None:
	if not name:
		return
	if not frappe.db.exists(doctype, name):
		frappe.throw(_("{0} {1} does not exist.").format(label, name), frappe.ValidationError)
	meta = frappe.get_meta(doctype)
	if meta.has_field("disabled") and cint(frappe.db.get_value(doctype, name, "disabled")):
		frappe.throw(_("{0} {1} is disabled and cannot be selected.").format(label, name), frappe.ValidationError)
	if meta.has_field("is_active") and not cint(frappe.db.get_value(doctype, name, "is_active")):
		frappe.throw(_("{0} {1} is inactive and cannot be selected.").format(label, name), frappe.ValidationError)


def _validate_sales_item(item_code: str | None, label: str, *, allow_stock: bool) -> None:
	if not item_code:
		return
	row = frappe.db.get_value("Item", item_code, ["disabled", "is_sales_item", "is_stock_item"], as_dict=True)
	if not row:
		frappe.throw(_("{0} {1} does not exist.").format(label, item_code), frappe.ValidationError)
	if cint(row.disabled) or not cint(row.is_sales_item):
		frappe.throw(_("{0} must be an enabled ERPNext sales Item.").format(label), frappe.ValidationError)
	if not allow_stock and cint(row.is_stock_item):
		frappe.throw(_("{0} must be a non-stock ERPNext Item.").format(label), frappe.ValidationError)


def _validate_price_list(price_list: str | None) -> None:
	if not price_list:
		return
	if not frappe.db.exists("Price List", price_list):
		frappe.throw(_("Price List {0} does not exist.").format(price_list), frappe.ValidationError)
	meta = frappe.get_meta("Price List")
	if meta.has_field("enabled") and not cint(frappe.db.get_value("Price List", price_list, "enabled")):
		frappe.throw(_("Price List {0} is disabled.").format(price_list), frappe.ValidationError)
	if meta.has_field("selling") and not cint(frappe.db.get_value("Price List", price_list, "selling")):
		frappe.throw(_("Price List {0} must be a selling Price List.").format(price_list), frappe.ValidationError)


def _validate_values(config: dict[str, Any], values: dict[str, Any]) -> None:
	key = config["key"]
	_validate_price_list(values.get("price_list"))
	if key == "treatment-items":
		_validate_sales_item(values.get("item"), _("ERPNext Item"), allow_stock=True)
		_assert_active_link("Veterinary Service Type", values.get("service_type"), _("Service Type"))
		_assert_active_link("Veterinary Treatment Type", values.get("treatment_type"), _("Treatment Type"))
		if values.get("default_price") not in (None, "") and flt(values.get("default_price")) < 0:
			frappe.throw(_("Default Price cannot be negative."), frappe.ValidationError)
		if values.get("shelf_life_in_days") not in (None, "") and cint(values.get("shelf_life_in_days")) < 0:
			frappe.throw(_("Shelf Life in Days cannot be negative."), frappe.ValidationError)
	elif key == "treatment-types":
		_validate_sales_item(values.get("default_item"), _("Default ERPNext Item"), allow_stock=True)
	elif key == "lab-tests":
		_validate_sales_item(values.get("linked_item"), _("Linked Billing Item"), allow_stock=False)
		if values.get("default_rate") not in (None, "") and flt(values.get("default_rate")) < 0:
			frappe.throw(_("Default Price cannot be negative."), frappe.ValidationError)
	elif key == "vaccines":
		_assert_active_link("Veterinary Species", values.get("species"), _("Species"))
		_validate_sales_item(values.get("default_item"), _("Default Item"), allow_stock=True)
		for fieldname, label in (
			("default_price", _("Default Price")),
			("default_validity_days", _("Default Validity Days")),
			("default_next_due_days", _("Default Next Due Days")),
		):
			value = values.get(fieldname)
			if value not in (None, "") and flt(value) < 0:
				frappe.throw(_("{0} cannot be negative.").format(label), frappe.ValidationError)
	elif key == "grooming-services":
		_validate_sales_item(values.get("default_item"), _("Default Item"), allow_stock=False)
		if values.get("default_rate") not in (None, "") and flt(values.get("default_rate")) < 0:
			frappe.throw(_("Default Rate cannot be negative."), frappe.ValidationError)
		if values.get("estimated_duration") not in (None, "") and flt(values.get("estimated_duration")) < 0:
			frappe.throw(_("Estimated Duration cannot be negative."), frappe.ValidationError)


def _apply_values(doc, meta, config: dict[str, Any], values: dict[str, Any]) -> None:
	allowed = _writable_fieldnames(meta, config, is_new=doc.is_new())
	for fieldname, value in values.items():
		if fieldname in allowed:
			doc.set(fieldname, value)


def _record_state(doc, meta) -> str:
	if meta.has_field("disabled"):
		return _("Disabled") if cint(doc.get("disabled")) else _("Active")
	if meta.has_field("is_active"):
		return _("Active") if cint(doc.get("is_active")) else _("Inactive")
	return _("Active")


@frappe.whitelist()
def get_pricing_master_definition(resource: str) -> dict[str, Any]:
	config = _require_resource(resource)
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
		"notice": config.get("notice") or "",
		"side_effects": config.get("side_effects") or [],
		"permissions": _permissions(doctype),
		"columns": _column_schema(meta, config.get("list_fields") or ["name", "modified"]),
		"filters": _filter_schema(meta, config.get("filter_fields") or []),
	}


@frappe.whitelist()
def get_pricing_master_list(
	resource: str,
	search: str = "",
	filters: str | dict | None = None,
	start: int = 0,
	page_length: int = 25,
) -> dict[str, Any]:
	config = _require_resource(resource)
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
def get_pricing_master_document(resource: str, name: str | None = None) -> dict[str, Any]:
	config = _require_resource(resource)
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
	schema = _build_form_schema(meta, config, is_new=is_new)
	return {
		"resource": config["key"],
		"doctype": doctype,
		"name": None if is_new else doc.name,
		"is_new": is_new,
		"title": config["singular"] if is_new else (doc.get(meta.title_field) if meta.title_field else doc.name),
		"schema": schema,
		"values": _document_values(doc, schema),
		"docstatus": cint(doc.docstatus),
		"state": _record_state(doc, meta),
		"notice": config.get("notice") or "",
		"side_effects": config.get("side_effects") or [],
		"permissions": _permissions(doctype, doc if not is_new else None),
		"modified": None if is_new else doc.modified,
	}


@frappe.whitelist()
def save_pricing_master_document(
	resource: str,
	values: str | dict,
	name: str | None = None,
	modified: str | None = None,
) -> dict[str, Any]:
	config = _require_resource(resource)
	doctype = config["doctype"]
	require_vetedge_platform_access(
		action="save_pricing_master_workspace",
		reference_doctype=doctype,
		reference_name=name,
	)
	meta = frappe.get_meta(doctype)
	payload = _parse_json_object(values)
	_validate_values(config, payload)
	if name:
		doc = frappe.get_doc(doctype, name)
		doc.check_permission("write")
		if modified and str(doc.modified) != str(modified):
			frappe.throw(
				_("This pricing master changed after you opened it. Reload before saving."),
				frappe.TimestampMismatchError,
			)
	else:
		if not frappe.has_permission(doctype, "create"):
			frappe.throw(_("You are not permitted to create {0}.").format(doctype), frappe.PermissionError)
		doc = frappe.new_doc(doctype)
	_apply_values(doc, meta, config, payload)
	if doc.is_new():
		doc.insert()
	else:
		doc.save()
	return get_pricing_master_document(config["key"], doc.name)


@frappe.whitelist()
def delete_pricing_master_document(resource: str, name: str) -> dict[str, Any]:
	config = _require_resource(resource)
	doctype = config["doctype"]
	require_vetedge_platform_access(
		action="delete_pricing_master_workspace",
		reference_doctype=doctype,
		reference_name=name,
	)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("delete")
	frappe.delete_doc(doctype, name)
	return {"deleted": True, "name": name}


@frappe.whitelist()
def get_pricing_master_link_options(
	resource: str,
	fieldname: str,
	query: str = "",
	page_length: int = 20,
) -> list[dict[str, Any]]:
	config = _require_resource(resource)
	meta = frappe.get_meta(config["doctype"])
	field = meta.get_field(fieldname)
	if not field or field.fieldtype != "Link":
		frappe.throw(_("This field does not support record lookup."), frappe.ValidationError)
	options = field.options
	if not options or not frappe.db.exists("DocType", options):
		return []
	if not frappe.has_permission(options, "read"):
		return []
	option_meta = frappe.get_meta(options)
	filters = {
		key: value
		for key, value in dict((config.get("link_filters") or {}).get(fieldname) or {}).items()
		if option_meta.has_field(key)
	}
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
