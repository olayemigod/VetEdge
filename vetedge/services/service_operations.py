from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from vetedge.services.permissions import (
	can_access_branch_data,
	get_assigned_branches,
	get_current_user,
	user_has_global_branch_access,
)
from vetedge.services.platform_access import require_vetedge_platform_access
from vetedge.services.portal_access import require_internal_user

PAGE_LENGTH_MAX = 100

RESOURCE_CONFIG: dict[str, dict[str, Any]] = {
	"boarding-stays": {
		"doctype": "Pet Boarding Stay",
		"title": _("Boarding Stays"),
		"subtitle": _("Review active and completed boarding stays, kennel assignment and care-record activity."),
		"fields": [
			"name", "booking", "patient", "primary_owner", "service_branch", "kennel",
			"check_in_datetime", "check_out_datetime", "status", "feeding_instructions", "special_notes", "modified",
		],
		"columns": [
			("name", _("Stay"), "Data"), ("patient", _("Patient"), "Link"),
			("service_branch", _("Branch"), "Link"), ("kennel", _("Kennel"), "Link"),
			("check_in_datetime", _("Check In"), "Datetime"), ("status", _("Status"), "status"),
		],
		"search_fields": ["name", "booking", "patient", "primary_owner", "kennel", "status"],
	},
	"boarding-care-records": {
		"doctype": "Pet Boarding Care Record",
		"title": _("Boarding Care Records"),
		"subtitle": _("Review feeding, hydration, exercise, elimination, mood and grooming observations recorded during boarding."),
		"fields": [
			"name", "stay", "booking", "patient", "primary_owner", "service_branch", "kennel",
			"care_datetime", "care_type", "record_status", "recorded_by", "feeding_status",
			"appetite_status", "food_portion_percent", "water_intake_ml", "walk_status",
			"walk_duration_minutes", "elimination_status", "mood_status", "grooming_check_status", "notes", "modified",
		],
		"columns": [
			("care_datetime", _("Care Date/Time"), "Datetime"), ("patient", _("Patient"), "Link"),
			("care_type", _("Care Type"), "Data"), ("record_status", _("Status"), "status"),
			("kennel", _("Kennel"), "Link"), ("recorded_by", _("Recorded By"), "Link"),
		],
		"search_fields": ["name", "stay", "booking", "patient", "kennel", "care_type", "record_status", "recorded_by"],
	},
	"grooming-sessions": {
		"doctype": "Pet Grooming Session",
		"title": _("Grooming Sessions"),
		"subtitle": _("Run grooming sessions and keep their workflow and billing state visible inside the Veterinary workspace."),
		"fields": [
			"name", "patient", "primary_owner", "status", "service_branch", "appointment",
			"grooming_service", "groomer", "groomer_name", "start_time", "end_time",
			"pre_grooming_notes", "post_grooming_notes", "linked_invoice", "modified",
		],
		"columns": [
			("name", _("Session"), "Data"), ("patient", _("Patient"), "Link"),
			("grooming_service", _("Service"), "Link"), ("groomer_name", _("Groomer"), "Data"),
			("start_time", _("Start"), "Datetime"), ("status", _("Status"), "status"),
		],
		"search_fields": ["name", "patient", "primary_owner", "status", "grooming_service", "groomer", "groomer_name"],
	},
}

CARE_FIELDS = {
	"care_datetime", "care_type", "record_status", "feeding_status", "appetite_status",
	"food_portion_percent", "water_intake_ml", "walk_status", "walk_duration_minutes",
	"elimination_status", "mood_status", "grooming_check_status", "notes",
}


def _config(resource: str) -> dict[str, Any]:
	key = str(resource or "").strip()
	config = RESOURCE_CONFIG.get(key)
	if not config:
		frappe.throw(_("This Hospital & Services resource is not available."), frappe.ValidationError)
	return {"key": key, **config}


def _page_values(start: int, page_length: int) -> tuple[int, int]:
	return max(cint(start), 0), min(max(cint(page_length) or 25, 1), PAGE_LENGTH_MAX)


def _branch_filters(doctype: str, branch: str | None = None) -> dict:
	meta = frappe.get_meta(doctype)
	if not meta.has_field("service_branch"):
		return {}
	user = get_current_user() or frappe.session.user
	if branch:
		can_access_branch_data(user, branch, raise_exception=True)
		return {"service_branch": branch}
	if user_has_global_branch_access(user):
		return {}
	assigned = get_assigned_branches(user)
	return {"service_branch": ["in", assigned]} if assigned else {"service_branch": ["=", "__no_branch_access__"]}


def _count(doctype: str, filters: dict, or_filters: list | None = None) -> int:
	rows = frappe.get_list(
		doctype,
		fields=[{"COUNT": "*", "as": "total"}],
		filters=filters,
		or_filters=or_filters,
		limit_page_length=1,
	)
	return cint(rows[0].get("total")) if rows else 0


def _columns(config: dict[str, Any]) -> list[dict]:
	return [{"key": key, "label": label, "type": fieldtype} for key, label, fieldtype in config["columns"]]


def _detail_fields(doc, config: dict[str, Any]) -> list[dict]:
	meta = frappe.get_meta(config["doctype"])
	fields = []
	for fieldname in config["fields"]:
		if fieldname == "name":
			fields.append({"key": "name", "label": _("ID"), "type": "Data", "value": doc.name})
			continue
		if fieldname == "modified":
			fields.append({"key": "modified", "label": _("Modified"), "type": "Datetime", "value": doc.modified})
			continue
		field = meta.get_field(fieldname)
		if not field:
			continue
		fields.append({
			"key": fieldname,
			"label": field.label or fieldname.replace("_", " ").title(),
			"type": field.fieldtype,
			"value": doc.get(fieldname),
		})
	return fields


def _actions(resource: str, doc) -> list[dict]:
	actions: list[dict] = []
	if resource == "boarding-stays":
		actions.append({"key": "care-records", "label": _("View Care Records")})
		if doc.status == "Active" and frappe.has_permission("Pet Boarding Care Record", "create"):
			actions.append({"key": "add-care-record", "label": _("Add Care Record"), "primary": True})
	if resource == "grooming-sessions" and doc.has_permission("write"):
		if doc.status in {"Draft", "Awaiting Payment", "Pending Grooming"}:
			actions.append({"key": "start-grooming", "label": _("Start Grooming"), "primary": True})
		if doc.status == "In Progress":
			actions.append({"key": "complete-grooming", "label": _("Complete Grooming"), "primary": True})
		if doc.status not in {"Completed", "Cancelled"}:
			actions.append({"key": "cancel-grooming", "label": _("Cancel Session"), "danger": True})
		actions.append({"key": "billing", "label": _("Billing / Payment")})
	return actions


@frappe.whitelist()
def get_service_operations_page(
	resource: str,
	search: str = "",
	branch: str | None = None,
	parent: str | None = None,
	start: int = 0,
	page_length: int = 25,
) -> dict:
	require_internal_user()
	config = _config(resource)
	doctype = config["doctype"]
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("You are not permitted to view {0}.").format(doctype), frappe.PermissionError)

	filters = _branch_filters(doctype, branch)
	if parent:
		if resource == "boarding-care-records":
			filters["stay"] = parent
		elif resource == "grooming-sessions":
			filters["appointment"] = parent

	query = str(search or "").strip()
	or_filters = None
	if query:
		or_filters = [[doctype, fieldname, "like", f"%{query}%"] for fieldname in config["search_fields"]]
	start, page_length = _page_values(start, page_length)
	rows = frappe.get_list(
		doctype,
		fields=config["fields"],
		filters=filters,
		or_filters=or_filters,
		order_by="modified desc",
		start=start,
		page_length=page_length,
	)
	return {
		"resource": config["key"],
		"title": config["title"],
		"subtitle": config["subtitle"],
		"columns": _columns(config),
		"rows": rows,
		"total": _count(doctype, filters, or_filters),
		"start": start,
		"page_length": page_length,
	}


@frappe.whitelist()
def get_service_operation_detail(resource: str, name: str) -> dict:
	require_internal_user()
	config = _config(resource)
	doc = frappe.get_doc(config["doctype"], name)
	doc.check_permission("read")
	branch = doc.get("service_branch")
	if branch:
		can_access_branch_data(get_current_user(), branch, raise_exception=True)
	return {
		"resource": config["key"],
		"doctype": config["doctype"],
		"name": doc.name,
		"title": doc.get(getattr(doc.meta, "title_field", "")) or doc.name,
		"status": doc.get("status") or doc.get("record_status") or "",
		"modified": doc.modified,
		"fields": _detail_fields(doc, config),
		"actions": _actions(config["key"], doc),
	}


@frappe.whitelist()
def create_boarding_care_record(stay: str, values: dict | str | None = None) -> dict:
	require_internal_user()
	require_vetedge_platform_access(
		action="create_boarding_care_record",
		reference_doctype="Pet Boarding Stay",
		reference_name=stay,
	)
	stay_doc = frappe.get_doc("Pet Boarding Stay", stay)
	stay_doc.check_permission("read")
	if stay_doc.status != "Active":
		frappe.throw(_("Care records can only be added to an active boarding stay."), frappe.ValidationError)
	can_access_branch_data(get_current_user(), stay_doc.service_branch, raise_exception=True)
	if not frappe.has_permission("Pet Boarding Care Record", "create"):
		frappe.throw(_("You are not permitted to create boarding care records."), frappe.PermissionError)

	payload = frappe.parse_json(values or {})
	payload = payload if isinstance(payload, dict) else {}
	doc = frappe.get_doc({
		"doctype": "Pet Boarding Care Record",
		"stay": stay_doc.name,
		"booking": stay_doc.booking,
		"patient": stay_doc.patient,
		"primary_owner": stay_doc.primary_owner,
		"service_branch": stay_doc.service_branch,
		"kennel": stay_doc.kennel,
		"care_datetime": payload.get("care_datetime") or now_datetime(),
		"care_type": payload.get("care_type") or "Routine Check",
		"record_status": payload.get("record_status") or "Completed",
		**{key: payload.get(key) for key in CARE_FIELDS if key not in {"care_datetime", "care_type", "record_status"}},
	})
	doc.insert()
	return get_service_operation_detail("boarding-care-records", doc.name)


@frappe.whitelist()
def transition_grooming_session(session: str, status: str) -> dict:
	require_internal_user()
	from vetedge.services.grooming import transition_grooming_session_status

	transition_grooming_session_status(session, status)
	return get_service_operation_detail("grooming-sessions", session)
