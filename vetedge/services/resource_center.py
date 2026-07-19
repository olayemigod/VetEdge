from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

from vetedge.coreedge_adapter import get_current_vetedge_branch

PAGE_LENGTH_MAX = 100
SUPPORTED_FIELDTYPES = {
	"Data",
	"Small Text",
	"Text",
	"Long Text",
	"Select",
	"Check",
	"Int",
	"Float",
	"Currency",
	"Percent",
	"Date",
	"Datetime",
	"Time",
	"Link",
	"Phone",
	"Email",
}
SYSTEM_FIELDS = {
	"name",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"docstatus",
	"idx",
	"amended_from",
}

RESOURCE_CONFIG: dict[str, dict[str, Any]] = {
	"patients": {
		"doctype": "Veterinary Patient",
		"title": _("Patients"),
		"subtitle": _("Search and maintain veterinary patient records without leaving the Veterinary workspace."),
		"allow_create": True,
		"allow_edit": True,
		"allow_delete": False,
	},
	"appointments": {
		"doctype": "Veterinary Appointment",
		"title": _("Appointments"),
		"subtitle": _("Review and maintain appointment records. Workflow actions still use the dedicated appointment flow."),
		"allow_create": True,
		"allow_edit": True,
		"allow_delete": False,
	},
	"missed-appointments": {
		"doctype": "Veterinary Missed Appointment",
		"title": _("Missed Appointments"),
		"subtitle": _("Review missed appointments. Reschedule, cancel and resolve actions remain in the dedicated action center."),
		"allow_create": False,
		"allow_edit": False,
		"allow_delete": False,
	},
	"consultations": {
		"doctype": "Veterinary Consultation",
		"title": _("Consultations"),
		"subtitle": _("Permission-safe consultation register. Clinical workflow and billing continue in the dedicated consultation screen."),
		"allow_create": False,
		"allow_edit": False,
		"allow_delete": False,
	},
	"lab-orders": {
		"doctype": "Veterinary Lab Order",
		"title": _("Laboratory Orders"),
		"subtitle": _("Review laboratory orders. Results, billing and payment-safe actions remain in the dedicated laboratory workflow."),
		"allow_create": False,
		"allow_edit": False,
		"allow_delete": False,
	},
	"vaccinations": {
		"doctype": "Veterinary Vaccination Record",
		"title": _("Vaccination Records"),
		"subtitle": _("Review vaccination history and due dates. Stock and billing actions remain in the vaccination workflow."),
		"allow_create": False,
		"allow_edit": False,
		"allow_delete": False,
	},
	"grooming": {
		"doctype": "Pet Grooming Appointment",
		"title": _("Grooming Appointments"),
		"subtitle": _("Review and maintain grooming bookings. Billing and service completion stay in the dedicated workflow."),
		"allow_create": True,
		"allow_edit": True,
		"allow_delete": False,
	},
	"boarding": {
		"doctype": "Pet Boarding Booking",
		"title": _("Boarding Bookings"),
		"subtitle": _("Review and maintain boarding reservations. Admission, care and billing remain in dedicated pages."),
		"allow_create": True,
		"allow_edit": True,
		"allow_delete": False,
	},
	"kennels": {
		"doctype": "Kennel",
		"title": _("Kennels and Care Locations"),
		"subtitle": _("Maintain available kennels and care locations with branch-safe validation."),
		"allow_create": True,
		"allow_edit": True,
		"allow_delete": True,
	},
}


def _require_login() -> None:
	if frappe.session.user == "Guest":
		frappe.throw(_("Authentication required."), frappe.PermissionError)


def _resource(resource: str) -> dict[str, Any]:
	key = str(resource or "").strip()
	config = RESOURCE_CONFIG.get(key)
	if not config:
		frappe.throw(_("This Veterinary resource is not available."), frappe.PermissionError)
	if not frappe.db.exists("DocType", config["doctype"]):
		frappe.throw(_("{0} is not installed on this site.").format(config["doctype"]))
	return {"key": key, **config}


def _parse_values(values: str | dict | None) -> dict:
	if not values:
		return {}
	if isinstance(values, dict):
		return values
	parsed = frappe.parse_json(values)
	if not isinstance(parsed, dict):
		frappe.throw(_("Expected a JSON object."), frappe.ValidationError)
	return parsed


def _meta_fields(meta) -> list:
	return [
		field
		for field in meta.fields
		if field.fieldname
		and field.fieldname not in SYSTEM_FIELDS
		and field.fieldtype in SUPPORTED_FIELDTYPES
		and not field.hidden
		and not field.read_only
		and not getattr(field, "virtual", False)
	]


def _editor_fields(meta) -> list[dict]:
	fields = _meta_fields(meta)
	preferred = [field for field in fields if field.reqd or field.in_list_view or field.in_standard_filter]
	remaining = [field for field in fields if field not in preferred]
	selected = (preferred + remaining)[:24]
	return [
		{
			"fieldname": field.fieldname,
			"fieldtype": field.fieldtype,
			"label": field.label or field.fieldname.replace("_", " ").title(),
			"options": field.options or "",
			"reqd": cint(field.reqd),
			"description": field.description or "",
			"default": field.default,
			"depends_on": field.depends_on or "",
			"mandatory_depends_on": field.mandatory_depends_on or "",
		}
		for field in selected
	]


def _unsupported_required_fields(meta) -> list[str]:
	return [
		field.label or field.fieldname
		for field in meta.fields
		if field.fieldname
		and field.fieldname not in SYSTEM_FIELDS
		and field.reqd
		and not field.read_only
		and field.fieldtype not in SUPPORTED_FIELDTYPES
	]


def _list_fields(meta) -> list[str]:
	fields = ["name"]
	for fieldname in (meta.title_field, "status", "branch", "company"):
		if fieldname and meta.has_field(fieldname) and fieldname not in fields:
			fields.append(fieldname)
	for field in meta.fields:
		if field.in_list_view and field.fieldname and field.fieldname not in fields:
			fields.append(field.fieldname)
		if len(fields) >= 7:
			break
	if meta.is_submittable and "docstatus" not in fields:
		fields.append("docstatus")
	fields.append("modified")
	return fields


def _search_fields(meta, list_fields: list[str]) -> list[str]:
	fields = ["name"]
	for fieldname in list_fields:
		field = meta.get_field(fieldname)
		if field and field.fieldtype in {"Data", "Small Text", "Text", "Link", "Select"}:
			fields.append(fieldname)
	return list(dict.fromkeys(fields))[:5]


def _branch_filters(meta) -> dict:
	if not meta.has_field("branch"):
		return {}
	try:
		branch = get_current_vetedge_branch()
	except Exception:
		branch = None
	if branch and str(branch).strip().lower() not in {"all", "all branches"}:
		return {"branch": branch}
	return {}


def _full_form_route(doctype: str, name: str | None = None) -> str:
	slug = frappe.scrub(doctype).replace("_", "-")
	return f"/app/{slug}/{name}" if name else f"/app/{slug}"


def _column_schema(meta, fields: list[str]) -> list[dict]:
	columns = []
	for fieldname in fields:
		if fieldname == "name":
			columns.append({"fieldname": "name", "label": _("ID"), "fieldtype": "Data"})
			continue
		if fieldname == "modified":
			columns.append({"fieldname": "modified", "label": _("Modified"), "fieldtype": "Datetime"})
			continue
		if fieldname == "docstatus":
			columns.append({"fieldname": "docstatus", "label": _("Document Status"), "fieldtype": "Int"})
			continue
		field = meta.get_field(fieldname)
		columns.append(
			{
				"fieldname": fieldname,
				"label": field.label or fieldname.replace("_", " ").title(),
				"fieldtype": field.fieldtype,
			}
		)
	return columns


def _permission_aware_count(doctype: str, filters: dict, or_filters: list | None) -> int:
	rows = frappe.get_list(
		doctype,
		fields=["count(name) as total"],
		filters=filters,
		or_filters=or_filters,
		limit_page_length=1,
	)
	return cint(rows[0].get("total")) if rows else 0


@frappe.whitelist()
def get_resource_page(
	resource: str,
	search: str = "",
	start: int = 0,
	page_length: int = 25,
) -> dict:
	_require_login()
	config = _resource(resource)
	doctype = config["doctype"]
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("You are not permitted to view {0}.").format(doctype), frappe.PermissionError)

	meta = frappe.get_meta(doctype)
	fields = _list_fields(meta)
	filters = _branch_filters(meta)
	or_filters = None
	query = str(search or "").strip()
	if query:
		or_filters = [[doctype, fieldname, "like", f"%{query}%"] for fieldname in _search_fields(meta, fields)]

	page_length = min(max(cint(page_length) or 25, 1), PAGE_LENGTH_MAX)
	start = max(cint(start), 0)
	rows = frappe.get_list(
		doctype,
		fields=fields,
		filters=filters,
		or_filters=or_filters,
		order_by="modified desc",
		start=start,
		page_length=page_length,
	)
	total = _permission_aware_count(doctype, filters, or_filters)
	unsupported = _unsupported_required_fields(meta)
	can_create = bool(config["allow_create"] and frappe.has_permission(doctype, "create") and not unsupported)
	can_quick_edit = bool(
		config["allow_edit"] and frappe.has_permission(doctype, "write") and not unsupported
	)
	can_delete = bool(config["allow_delete"] and frappe.has_permission(doctype, "delete"))

	return {
		"resource": config["key"],
		"doctype": doctype,
		"title": config["title"],
		"subtitle": config["subtitle"],
		"columns": _column_schema(meta, fields),
		"rows": rows,
		"start": start,
		"page_length": page_length,
		"total": total,
		"can_create": can_create,
		"can_quick_edit": can_quick_edit,
		"can_delete": can_delete,
		"unsupported_required_fields": unsupported,
		"full_form_route": _full_form_route(doctype),
	}


@frappe.whitelist()
def get_resource_editor(resource: str, name: str | None = None) -> dict:
	_require_login()
	config = _resource(resource)
	doctype = config["doctype"]
	meta = frappe.get_meta(doctype)
	unsupported = _unsupported_required_fields(meta)
	if unsupported:
		frappe.throw(
			_("Quick editing is unavailable because these required fields need the full ERPNext form: {0}").format(
				", ".join(unsupported)
			)
		)

	fields = _editor_fields(meta)
	if name:
		doc = frappe.get_doc(doctype, name)
		doc.check_permission("read")
		can_save = bool(config["allow_edit"] and doc.docstatus == 0 and doc.has_permission("write"))
		values = {field["fieldname"]: doc.get(field["fieldname"]) for field in fields}
	else:
		if not config["allow_create"] or not frappe.has_permission(doctype, "create"):
			frappe.throw(_("You are not permitted to create {0}.").format(doctype), frappe.PermissionError)
		can_save = True
		values = {}
		if meta.has_field("branch"):
			values["branch"] = get_current_vetedge_branch()

	return {
		"resource": config["key"],
		"doctype": doctype,
		"name": name,
		"title": _("Update {0}").format(config["title"]) if name else _("Add {0}").format(config["title"]),
		"fields": fields,
		"values": values,
		"can_save": can_save,
		"full_form_route": _full_form_route(doctype, name),
	}


@frappe.whitelist()
def save_resource_record(resource: str, values: str | dict, name: str | None = None) -> dict:
	_require_login()
	config = _resource(resource)
	doctype = config["doctype"]
	meta = frappe.get_meta(doctype)
	allowed_fields = {field["fieldname"] for field in _editor_fields(meta)}
	payload = {key: value for key, value in _parse_values(values).items() if key in allowed_fields}

	if name:
		doc = frappe.get_doc(doctype, name)
		if not config["allow_edit"] or doc.docstatus != 0:
			frappe.throw(_("This record cannot be edited in the quick editor."), frappe.PermissionError)
		doc.check_permission("write")
		doc.update(payload)
		doc.save()
	else:
		if not config["allow_create"] or not frappe.has_permission(doctype, "create"):
			frappe.throw(_("You are not permitted to create {0}.").format(doctype), frappe.PermissionError)
		if meta.has_field("branch") and not payload.get("branch"):
			payload["branch"] = get_current_vetedge_branch()
		doc = frappe.get_doc({"doctype": doctype, **payload})
		doc.insert()

	return {
		"name": doc.name,
		"doctype": doctype,
		"full_form_route": _full_form_route(doctype, doc.name),
	}


@frappe.whitelist()
def delete_resource_record(resource: str, name: str) -> dict:
	_require_login()
	config = _resource(resource)
	if not config["allow_delete"]:
		frappe.throw(_("Deletion is not available for this resource."), frappe.PermissionError)

	doc = frappe.get_doc(config["doctype"], name)
	if doc.docstatus != 0:
		frappe.throw(_("Submitted records cannot be deleted."), frappe.ValidationError)
	doc.check_permission("delete")
	frappe.delete_doc(config["doctype"], name)
	return {"deleted": True, "name": name}
