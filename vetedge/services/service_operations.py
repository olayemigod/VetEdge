from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from vetedge.services.display_labels import enrich_link_display_values, get_display_label
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
	"boarding-bookings": {
		"doctype": "Pet Boarding Booking",
		"title": _("Boarding Bookings"),
		"subtitle": _("Create and manage boarding reservations, billing, check-in and check-out from the Veterinary workspace."),
		"editor_resource": "boarding",
		"fields": [
			"name", "patient", "primary_owner", "service_branch", "kennel", "check_in_date",
			"expected_check_out_date", "actual_check_out_date", "status", "billing_item", "daily_rate",
			"billable_days", "total_boarding_charge", "linked_invoice", "linked_stay", "feeding_instructions",
			"special_notes", "modified",
		],
		"columns": [
			("name", _("Booking"), "Data"), ("patient", _("Patient"), "Link"),
			("service_branch", _("Branch"), "Link"), ("kennel", _("Kennel"), "Link"),
			("check_in_date", _("Check In"), "Date"), ("expected_check_out_date", _("Expected Check-Out"), "Date"),
			("status", _("Status"), "status"),
		],
		"search_fields": ["name", "patient", "primary_owner", "service_branch", "kennel", "status", "linked_invoice"],
	},
	"boarding-stays": {
		"doctype": "Pet Boarding Stay",
		"title": _("Boarding Stays"),
		"subtitle": _("Review active and completed boarding stays, kennel assignment and care-record activity."),
		"entry_editor_resource": "boarding",
		"entry_doctype": "Pet Boarding Booking",
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
	"grooming-appointments": {
		"doctype": "Pet Grooming Appointment",
		"title": _("Grooming Appointments"),
		"subtitle": _("Create and maintain grooming appointments before progressing into the grooming session workflow."),
		"editor_resource": "grooming",
		"fields": [
			"name", "patient", "primary_owner", "status", "scheduled_datetime", "service_branch",
			"grooming_service", "groomer", "groomer_name", "notes", "linked_invoice", "modified",
		],
		"columns": [
			("name", _("Appointment"), "Data"), ("patient", _("Patient"), "Link"),
			("grooming_service", _("Service"), "Link"), ("groomer_name", _("Groomer"), "Data"),
			("scheduled_datetime", _("Scheduled"), "Datetime"), ("status", _("Status"), "status"),
		],
		"search_fields": ["name", "patient", "primary_owner", "status", "grooming_service", "groomer", "groomer_name"],
	},
	"grooming-sessions": {
		"doctype": "Pet Grooming Session",
		"title": _("Grooming Sessions"),
		"subtitle": _("Run grooming sessions and keep their workflow and billing state visible inside the Veterinary workspace."),
		"entry_editor_resource": "grooming",
		"entry_doctype": "Pet Grooming Appointment",
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
	meta = frappe.get_meta(config["doctype"])
	columns = []
	for key, label, fieldtype in config["columns"]:
		column = {
			"key": key,
			"fieldname": key,
			"label": label,
			"type": fieldtype,
			"fieldtype": fieldtype,
		}
		field = meta.get_field(key)
		if field and field.fieldtype == "Link":
			column["options"] = field.options or ""
		columns.append(column)
	return columns


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
		value = doc.get(fieldname)
		payload = {
			"key": fieldname,
			"label": field.label or fieldname.replace("_", " ").title(),
			"type": field.fieldtype,
			"value": value,
		}
		if field.fieldtype == "Link" and field.options and value:
			payload["raw_value"] = value
			payload["value"] = get_display_label(field.options, value)
		fields.append(payload)
	return fields


def _document_title(doc) -> str:
	title_field = getattr(doc.meta, "title_field", "") or ""
	value = doc.get(title_field) if title_field else None
	if not value:
		return doc.name
	field = doc.meta.get_field(title_field)
	if field and field.fieldtype == "Link" and field.options:
		return get_display_label(field.options, value)
	return str(value)


def _has_billing_core_evidence(source_doctype: str, source_name: str) -> bool:
	if not frappe.db.exists("DocType", "Veterinary Billing Session Charge"):
		return False
	return bool(
		frappe.get_all(
			"Veterinary Billing Session Charge",
			filters={"source_doctype": source_doctype, "source_name": source_name},
			fields=["name"],
			limit=1,
		)
	)


def _has_financial_evidence(doc) -> bool:
	if doc.get("linked_invoice"):
		return True
	if doc.doctype == "Pet Boarding Booking" and doc.get("booking_invoices"):
		return True
	return _has_billing_core_evidence(doc.doctype, doc.name)


def _can_delete_service_order(resource: str, doc) -> bool:
	if resource not in {"boarding-bookings", "grooming-appointments"}:
		return False
	if not doc.has_permission("delete") or _has_financial_evidence(doc):
		return False
	if resource == "boarding-bookings":
		return doc.status == "Draft" and not doc.get("linked_stay")
	if doc.status != "Scheduled":
		return False
	return not frappe.db.exists("Pet Grooming Session", {"appointment": doc.name})


def _archive_and_detach_notifications(reference_doctype: str, reference_name: str) -> None:
	if not frappe.db.exists("DocType", "Veterinary Notification Item"):
		return
	meta = frappe.get_meta("Veterinary Notification Item")
	filters = {"reference_doctype": reference_doctype, "reference_name": reference_name}
	for row in frappe.get_all("Veterinary Notification Item", filters=filters, fields=["name"]):
		values = {}
		if meta.has_field("status"):
			values["status"] = "Archived"
		if meta.has_field("reference_doctype"):
			values["reference_doctype"] = None
		if meta.has_field("reference_name"):
			values["reference_name"] = None
		if values:
			frappe.db.set_value("Veterinary Notification Item", row.name, values, update_modified=False)


def _actions(resource: str, doc) -> list[dict]:
	actions: list[dict] = []
	can_write = bool(doc.has_permission("write"))

	if resource == "boarding-bookings":
		if can_write and doc.status in {"Draft", "Reserved"}:
			actions.append({"key": "edit-guided", "label": _("Edit Booking")})
		if can_write and doc.status != "Cancelled":
			actions.append({"key": "billing", "label": _("Billing / Payment")})
		if can_write and doc.status == "Draft":
			actions.append({"key": "reserve-boarding", "label": _("Reserve"), "primary": True})
		if can_write and doc.status == "Reserved":
			actions.append({"key": "check-in-boarding", "label": _("Check In"), "primary": True})
		if can_write and doc.status == "Checked In":
			actions.append({"key": "check-out-boarding", "label": _("Check Out"), "primary": True})
		if can_write and doc.status in {"Draft", "Reserved"} and not _has_financial_evidence(doc):
			actions.append({"key": "cancel-boarding", "label": _("Cancel Booking"), "danger": True})
		if doc.get("linked_stay"):
			actions.append({"key": "open-stay", "label": _("Open Stay"), "target_name": doc.linked_stay})
		if _can_delete_service_order(resource, doc):
			actions.append({"key": "delete-order", "label": _("Delete Draft"), "danger": True})

	if resource == "boarding-stays":
		actions.append({"key": "care-records", "label": _("View Care Records")})
		if doc.get("booking"):
			actions.append({"key": "open-booking", "label": _("Open Booking"), "target_name": doc.booking})
			actions.append({
				"key": "billing-target", "label": _("Billing / Payment"),
				"target_doctype": "Pet Boarding Booking", "target_name": doc.booking,
			})
		if doc.status == "Active" and frappe.has_permission("Pet Boarding Care Record", "create"):
			actions.append({"key": "add-care-record", "label": _("Add Care Record"), "primary": True})

	if resource == "grooming-appointments":
		if can_write and doc.status not in {"Completed", "Cancelled", "No Show"}:
			actions.append({"key": "edit-guided", "label": _("Edit Appointment")})
		if doc.status not in {"Completed", "Cancelled", "No Show"} and frappe.has_permission("Pet Grooming Session", "create"):
			actions.append({"key": "create-grooming-session", "label": _("Create / Open Session"), "primary": True})
		if _can_delete_service_order(resource, doc):
			actions.append({"key": "delete-order", "label": _("Delete Appointment"), "danger": True})

	if resource == "grooming-sessions" and can_write:
		if doc.get("appointment"):
			actions.append({"key": "open-grooming-appointment", "label": _("Open Appointment"), "target_name": doc.appointment})
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
	columns = _columns(config)
	enrich_link_display_values(rows, columns)
	editor_resource = config.get("editor_resource") or config.get("entry_editor_resource") or ""
	create_doctype = config.get("entry_doctype") or doctype
	can_create = bool(editor_resource and create_doctype and frappe.has_permission(create_doctype, "create"))
	return {
		"resource": config["key"],
		"title": config["title"],
		"subtitle": config["subtitle"],
		"columns": columns,
		"rows": rows,
		"total": _count(doctype, filters, or_filters),
		"start": start,
		"page_length": page_length,
		"can_create": can_create,
		"editor_resource": editor_resource,
		"create_doctype": create_doctype if can_create else "",
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
		"title": _document_title(doc),
		"status": doc.get("status") or doc.get("record_status") or "",
		"modified": doc.modified,
		"editor_resource": config.get("editor_resource") or "",
		"fields": _detail_fields(doc, config),
		"actions": _actions(config["key"], doc),
	}


@frappe.whitelist()
def transition_boarding_booking(booking: str, action: str) -> dict:
	require_internal_user()
	require_vetedge_platform_access(
		action=f"boarding_{action}",
		reference_doctype="Pet Boarding Booking",
		reference_name=booking,
	)
	doc = frappe.get_doc("Pet Boarding Booking", booking)
	doc.check_permission("write")
	can_access_branch_data(get_current_user(), doc.service_branch, raise_exception=True)

	from vetedge.services.boarding import (
		cancel_boarding_booking_doc,
		check_in_boarding_booking_doc,
		reserve_boarding_booking_doc,
	)
	from vetedge.services.boarding_checkout_alignment import check_out_boarding_booking_doc_aligned

	handlers = {
		"reserve": reserve_boarding_booking_doc,
		"check-in": check_in_boarding_booking_doc,
		"check-out": check_out_boarding_booking_doc_aligned,
		"cancel": cancel_boarding_booking_doc,
	}
	handler = handlers.get(str(action or "").strip())
	if not handler:
		frappe.throw(_("This boarding action is not available."), frappe.ValidationError)
	if action == "cancel" and _has_financial_evidence(doc):
		frappe.throw(
			_("This boarding booking already has billing history. Resolve or cancel its billing safely before cancelling the booking."),
			frappe.ValidationError,
		)
	handler(doc)
	return get_service_operation_detail("boarding-bookings", booking)


@frappe.whitelist()
def create_or_open_grooming_session(appointment: str) -> dict:
	require_internal_user()
	from vetedge.services.grooming import create_grooming_session_from_appointment

	result = create_grooming_session_from_appointment(appointment, create_invoice=0)
	return {
		**(result or {}),
		"detail": get_service_operation_detail("grooming-sessions", result.get("name")) if result and result.get("name") else None,
	}


@frappe.whitelist()
def delete_service_order(resource: str, name: str) -> dict:
	require_internal_user()
	config = _config(resource)
	if resource not in {"boarding-bookings", "grooming-appointments"}:
		frappe.throw(_("Deletion is not available for this service record."), frappe.PermissionError)
	require_vetedge_platform_access(
		action="delete_service_order",
		reference_doctype=config["doctype"],
		reference_name=name,
	)
	doc = frappe.get_doc(config["doctype"], name)
	doc.check_permission("delete")
	branch = doc.get("service_branch")
	if branch:
		can_access_branch_data(get_current_user(), branch, raise_exception=True)
	if not _can_delete_service_order(resource, doc):
		frappe.throw(
			_("This record cannot be deleted because it has progressed into service delivery or has billing history. Use the appropriate workflow action instead."),
			frappe.ValidationError,
		)
	_archive_and_detach_notifications(doc.doctype, doc.name)
	frappe.delete_doc(doc.doctype, doc.name)
	return {"deleted": True, "name": name, "resource": resource}


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
