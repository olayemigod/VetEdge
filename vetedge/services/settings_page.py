from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, cstr

SETTINGS_DOCTYPE = "Veterinary Settings"
LAYOUT_TYPES = {"Tab Break", "Section Break", "Column Break", "HTML", "Button"}
LOCKED_FIELDS = {"enable_vetedge"}
SERVICE_ITEM_FIELDS = {
	"consultation_item",
	"default_registration_item",
	"registration_item",
	"default_laboratory_service_item",
	"hospitalisation_admission_fee_item",
	"default_boarding_billing_item",
}
SUPPORTED_TYPES = {
	"Check",
	"Data",
	"Int",
	"Float",
	"Currency",
	"Percent",
	"Select",
	"Link",
	"Color",
	"Attach",
	"Attach Image",
	"Small Text",
	"Text",
	"Long Text",
	"Code",
	"Password",
	"Table",
}


def _require_permission(ptype: str) -> None:
	if not frappe.has_permission(SETTINGS_DOCTYPE, ptype=ptype):
		frappe.throw(_("You are not permitted to {0} Veterinary Settings.").format(ptype), frappe.PermissionError)


def _field_payload(field) -> dict:
	return {
		"fieldname": field.fieldname,
		"label": field.label or field.fieldname,
		"fieldtype": field.fieldtype,
		"options": field.options or "",
		"description": field.description or "",
		"depends_on": field.depends_on or "",
		"mandatory_depends_on": field.mandatory_depends_on or "",
		"read_only_depends_on": field.read_only_depends_on or "",
		"reqd": cint(field.reqd),
		"read_only": cint(field.read_only or field.fieldname in LOCKED_FIELDS),
		"permlevel": cint(field.permlevel),
		"precision": field.precision,
	}


def _child_meta(doctype: str) -> list[dict]:
	if not doctype or not frappe.db.exists("DocType", doctype):
		return []
	meta = frappe.get_meta(doctype)
	return [
		_field_payload(field)
		for field in meta.fields
		if field.fieldname
		and not field.hidden
		and field.fieldtype not in LAYOUT_TYPES
		and field.fieldtype in SUPPORTED_TYPES - {"Table"}
	]


def _schema() -> list[dict]:
	meta = frappe.get_meta(SETTINGS_DOCTYPE)
	tabs: list[dict] = []
	current_tab = {"fieldname": "setup", "label": _("Setup"), "sections": []}
	current_section = {"fieldname": "general", "label": _("General"), "description": "", "fields": []}
	tabs.append(current_tab)
	current_tab["sections"].append(current_section)

	for field in meta.fields:
		if field.hidden:
			continue
		if field.fieldtype == "Tab Break":
			current_tab = {
				"fieldname": field.fieldname,
				"label": field.label or field.fieldname,
				"sections": [],
			}
			tabs.append(current_tab)
			current_section = None
			continue
		if field.fieldtype == "Section Break":
			current_section = {
				"fieldname": field.fieldname,
				"label": field.label or field.fieldname,
				"description": field.description or "",
				"fields": [],
			}
			current_tab["sections"].append(current_section)
			continue
		if field.fieldtype in LAYOUT_TYPES or field.fieldtype not in SUPPORTED_TYPES:
			continue
		if current_section is None:
			current_section = {"fieldname": "general", "label": _("General"), "description": "", "fields": []}
			current_tab["sections"].append(current_section)
		payload = _field_payload(field)
		if field.fieldtype == "Table":
			payload["child_fields"] = _child_meta(field.options)
		current_section["fields"].append(payload)

	return [
		{**tab, "sections": [section for section in tab["sections"] if section["fields"]]}
		for tab in tabs
		if any(section["fields"] for section in tab["sections"])
	]


def _values(doc) -> dict:
	values = {}
	for tab in _schema():
		for section in tab["sections"]:
			for field in section["fields"]:
				value = doc.get(field["fieldname"])
				if field["fieldtype"] == "Table":
					values[field["fieldname"]] = [row.as_dict(no_nulls=True) for row in value or []]
				elif field["fieldtype"] == "Password":
					values[field["fieldname"]] = "" if not value else "********"
				else:
					values[field["fieldname"]] = value
	return values


def _modified(doc) -> str:
	return cstr(getattr(doc, "modified", "") or "")


def _write_roles() -> list[str]:
	meta = frappe.get_meta(SETTINGS_DOCTYPE)
	return sorted(
		{
			cstr(permission.role)
			for permission in meta.permissions
			if cint(permission.write) and cint(permission.permlevel) == 0 and permission.role
		}
	)


def _write_access_payload() -> dict:
	return {
		"can_write": bool(frappe.has_permission(SETTINGS_DOCTYPE, ptype="write")),
		"write_roles": _write_roles(),
	}


@frappe.whitelist()
def get_veterinary_settings_access() -> dict:
	_require_permission("read")
	return _write_access_payload()


@frappe.whitelist()
def get_veterinary_settings_page() -> dict:
	_require_permission("read")
	doc = frappe.get_single(SETTINGS_DOCTYPE)
	return {
		"doctype": SETTINGS_DOCTYPE,
		"schema": _schema(),
		"values": _values(doc),
		**_write_access_payload(),
		"modified": _modified(doc),
	}


def _clean_child_rows(field, rows) -> list[dict]:
	child_meta = frappe.get_meta(field.options)
	allowed = {
		child_field.fieldname
		for child_field in child_meta.fields
		if child_field.fieldname
		and child_field.fieldtype not in LAYOUT_TYPES
		and not child_field.read_only
		and child_field.fieldname not in LOCKED_FIELDS
	}
	cleaned = []
	for row in rows if isinstance(rows, list) else []:
		if not isinstance(row, dict):
			continue
		cleaned.append({key: value for key, value in row.items() if key in allowed})
	return cleaned


@frappe.whitelist()
def save_veterinary_settings_page(values=None, expected_modified: str | None = None) -> dict:
	_require_permission("write")
	if isinstance(values, str):
		values = json.loads(values)
	if not isinstance(values, dict):
		frappe.throw(_("Invalid Veterinary Settings payload."))

	doc = frappe.get_single(SETTINGS_DOCTYPE)
	if expected_modified and _modified(doc) != cstr(expected_modified):
		frappe.throw(
			_("Veterinary Settings changed after this page was opened. Refresh before saving."),
			frappe.TimestampMismatchError,
		)

	meta = frappe.get_meta(SETTINGS_DOCTYPE)
	for fieldname, value in values.items():
		field = meta.get_field(fieldname)
		if (
			not field
			or field.hidden
			or field.read_only
			or field.fieldname in LOCKED_FIELDS
			or field.fieldtype in LAYOUT_TYPES
		):
			continue
		if field.fieldtype == "Password" and value in (None, "", "********"):
			continue
		if field.fieldtype == "Table":
			doc.set(fieldname, [])
			for row in _clean_child_rows(field, value):
				doc.append(fieldname, row)
			continue
		doc.set(fieldname, value)

	doc.save()
	return {
		"message": _("Veterinary Settings saved."),
		"values": _values(doc),
		"modified": _modified(doc),
	}


def _link_filters(fieldname: str, target_doctype: str) -> dict:
	if target_doctype == "Item" and fieldname in SERVICE_ITEM_FIELDS:
		return {"disabled": 0, "is_sales_item": 1, "is_stock_item": 0}
	if target_doctype == "Price List":
		return {"enabled": 1, "selling": 1}
	return {}


def _resolve_settings_link_field(fieldname: str, child_fieldname: str | None = None):
	field = frappe.get_meta(SETTINGS_DOCTYPE).get_field(fieldname)
	if child_fieldname:
		if not field or field.fieldtype != "Table" or not field.options:
			frappe.throw(_("Invalid Veterinary Settings table field."), frappe.ValidationError)
		child_field = frappe.get_meta(field.options).get_field(child_fieldname)
		if not child_field or child_field.fieldtype != "Link" or not child_field.options:
			frappe.throw(_("Invalid Veterinary Settings child Link field."), frappe.ValidationError)
		return child_field
	if not field or field.fieldtype != "Link" or not field.options:
		frappe.throw(_("Invalid Veterinary Settings Link field."), frappe.ValidationError)
	return field


@frappe.whitelist()
def search_veterinary_settings_link(
	fieldname: str,
	txt: str = "",
	child_fieldname: str | None = None,
) -> list[dict]:
	_require_permission("read")
	field = _resolve_settings_link_field(fieldname, child_fieldname)
	filter_fieldname = child_fieldname or fieldname

	target_meta = frappe.get_meta(field.options)
	fields = ["name"]
	if target_meta.title_field and target_meta.title_field != "name":
		fields.append(target_meta.title_field)
	search_text = f"%{cstr(txt).strip()}%"
	or_filters = [["name", "like", search_text]]
	if target_meta.title_field and target_meta.title_field != "name":
		or_filters.append([target_meta.title_field, "like", search_text])
	rows = frappe.get_list(
		field.options,
		filters=_link_filters(filter_fieldname, field.options),
		or_filters=or_filters,
		fields=fields,
		limit_page_length=20,
	)
	return [
		{
			"value": row.get("name"),
			"label": row.get(target_meta.title_field) or row.get("name"),
			"description": row.get("name") if target_meta.title_field else "",
		}
		for row in rows
	]
