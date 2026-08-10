from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, now_datetime

from vetedge.services.appointment_flow import (
	ACTIVE_QUEUE_STATUSES,
	APPOINTMENT_STATUSES,
	cancel_missed_appointment,
	create_consultation_from_appointment,
	emit_appointment_status_notification,
	ensure_appointments_enabled,
	mark_missed_appointment_contacted,
	reopen_missed_appointment,
	reschedule_missed_appointment,
	resolve_missed_appointment,
	transition_appointment_status,
)
from vetedge.services.guest_booking import confirm_guest_registration, create_appointment_from_booking_request
from vetedge.services.permissions import (
	ELEVATED_ROLES,
	FRONT_DESK_ROLES,
	ROLE_BRANCH_MANAGER,
	can_access_branch_data,
	get_assigned_branches,
	get_current_user,
	user_has_any_role,
	user_has_global_branch_access,
)
from vetedge.services.platform_access import require_vetedge_platform_access
from vetedge.services.portal_access import require_internal_user

PAGE_LENGTH_MAX = 100
GUEST_ACTIVE_STATUSES = ("Registration Requested", "Registration Confirmed")
MISSED_ACTIVE_STATUSES = ("Open", "Contacted", "Reopened")
QUEUE_QUICK_ACTION_ROLES = {*ELEVATED_ROLES, *FRONT_DESK_ROLES, ROLE_BRANCH_MANAGER, "VetEdge Branch Manager", "VetEdge Doctor"}


def _require_front_desk_context() -> str:
	require_internal_user(); ensure_appointments_enabled(); return get_current_user() or frappe.session.user

def _parse_json_object(value: str | dict | None) -> dict[str, Any]:
	if not value: return {}
	if isinstance(value, dict): return value
	parsed = frappe.parse_json(value)
	if not isinstance(parsed, dict): frappe.throw(_("Expected a JSON object."), frappe.ValidationError)
	return parsed

def _page_values(start: int, page_length: int) -> tuple[int, int]: return max(cint(start), 0), min(max(cint(page_length) or 25, 1), PAGE_LENGTH_MAX)
def _assert_timestamp(doctype: str, name: str, expected_modified: str | None) -> None:
	if not expected_modified: return
	current = frappe.db.get_value(doctype, name, "modified")
	if current and str(current) != str(expected_modified): raise frappe.TimestampMismatchError(_("This record changed after it was opened. Refresh the Action Centre and try again."))
def _validate_branch(branch: str | None) -> None:
	if branch: can_access_branch_data(get_current_user(), branch, raise_exception=True)
def _branch_filters(branch: str | None = None) -> dict:
	_validate_branch(branch)
	if branch: return {"branch": branch}
	user = get_current_user()
	if user_has_global_branch_access(user): return {}
	assigned = get_assigned_branches(user); return {"branch": ["in", assigned]} if assigned else {}
def _guest_branch_filters(branch: str | None = None) -> dict:
	filters = _branch_filters(branch)
	if "branch" in filters: filters["preferred_branch"] = filters.pop("branch")
	return filters
def _count(doctype: str, filters: dict) -> int:
	rows = frappe.get_list(doctype, fields=[{"COUNT": "*", "as": "total"}], filters=filters, limit_page_length=1); return cint(rows[0].get("total")) if rows else 0
def _permission_count(doctype: str, filters: dict, or_filters: list | None = None) -> int:
	rows = frappe.get_list(doctype, fields=[{"COUNT": "*", "as": "total"}], filters=filters, or_filters=or_filters, limit_page_length=1); return cint(rows[0].get("total")) if rows else 0
def _row_title(doctype: str, name: str | None) -> str | None:
	if not name: return None
	meta = frappe.get_meta(doctype); fieldname = meta.title_field or "name"; return frappe.db.get_value(doctype, name, fieldname) or name

@frappe.whitelist()
def get_front_desk_summary(branch: str | None = None, reference_date: str | None = None) -> dict:
	_require_front_desk_context(); day = getdate(reference_date or now_datetime())
	queue_filters = {**_branch_filters(branch), "appointment_datetime": ["between", [f"{day} 00:00:00", f"{day} 23:59:59"]], "status": ["in", list(ACTIVE_QUEUE_STATUSES)]}
	guest_filters = {**_guest_branch_filters(branch), "status": ["in", list(GUEST_ACTIVE_STATUSES)]}; missed_filters = {**_branch_filters(branch), "resolved": 0, "status": ["in", list(MISSED_ACTIVE_STATUSES)]}
	return {"guest_requests": _count("Veterinary Guest Booking Request", guest_filters), "today_appointments": _count("Veterinary Appointment", queue_filters), "open_missed": _count("Veterinary Missed Appointment", missed_filters), "reference_date": str(day)}

@frappe.whitelist()
def get_guest_requests(search: str = "", status: str | None = None, branch: str | None = None, start: int = 0, page_length: int = 25) -> dict:
	_require_front_desk_context()
	if not frappe.has_permission("Veterinary Guest Booking Request", "read"): frappe.throw(_("You are not permitted to view guest booking requests."), frappe.PermissionError)
	filters = _guest_branch_filters(branch)
	if status: filters["status"] = status
	query = str(search or "").strip(); or_filters = [["Veterinary Guest Booking Request", fieldname, "like", f"%{query}%"] for fieldname in ("name", "guest_name", "guest_email", "guest_phone", "pet_name")] if query else None; start, page_length = _page_values(start, page_length)
	rows = frappe.get_list("Veterinary Guest Booking Request", fields=["name", "guest_name", "pet_name", "preferred_branch", "appointment_requested", "preferred_datetime", "status", "linked_patient", "linked_appointment", "modified"], filters=filters, or_filters=or_filters, order_by="modified desc", start=start, page_length=page_length)
	return {"rows": rows, "total": _permission_count("Veterinary Guest Booking Request", filters, or_filters), "start": start, "page_length": page_length}

@frappe.whitelist()
def get_guest_request_detail(name: str) -> dict:
	_require_front_desk_context(); doc = frappe.get_doc("Veterinary Guest Booking Request", name); doc.check_permission("read"); _validate_branch(doc.preferred_branch); actions = []; can_write = bool(doc.has_permission("write"))
	if can_write and doc.status not in {"Converted", "Cancelled"}:
		if not doc.linked_patient: actions += [{"key": "confirm_registration", "label": _("Confirm Registration"), "primary": True}, {"key": "cancel_request", "label": _("Cancel Request"), "danger": True}]
		elif doc.appointment_requested and not doc.linked_appointment: actions.append({"key": "create_appointment", "label": _("Create Appointment"), "primary": True})
	return {"name": doc.name, "modified": doc.modified, "status": doc.status, "can_write": can_write, "values": {"guest_name": doc.guest_name, "guest_email": doc.guest_email, "guest_phone": doc.guest_phone, "pet_name": doc.pet_name, "species": doc.species, "species_label": _row_title("Veterinary Species", doc.species), "breed": doc.breed, "breed_label": _row_title("Veterinary Breed", doc.breed), "preferred_branch": doc.preferred_branch, "appointment_requested": cint(doc.appointment_requested), "preferred_datetime": doc.preferred_datetime, "reason_for_visit": doc.reason_for_visit, "source": doc.source, "linked_customer": doc.linked_customer, "linked_patient": doc.linked_patient, "linked_appointment": doc.linked_appointment, "registration_invoice": doc.registration_invoice}, "actions": actions}

@frappe.whitelist()
def perform_guest_request_action(name: str, action: str, modified: str | None = None) -> dict:
	_require_front_desk_context(); doc = frappe.get_doc("Veterinary Guest Booking Request", name); doc.check_permission("write"); _validate_branch(doc.preferred_branch); _assert_timestamp(doc.doctype, doc.name, modified); require_vetedge_platform_access(action=f"front_desk_guest_{action}", reference_doctype=doc.doctype, reference_name=doc.name)
	if action == "confirm_registration": confirm_guest_registration(doc.name)
	elif action == "create_appointment": create_appointment_from_booking_request(doc.name)
	elif action == "cancel_request": _cancel_guest_request(doc)
	else: frappe.throw(_("Unsupported guest request action."), frappe.ValidationError)
	return get_guest_request_detail(doc.name)

def _cancel_guest_request(doc) -> None:
	if doc.status in {"Converted", "Cancelled"}: return
	if doc.linked_patient or doc.registration_invoice: frappe.throw(_("A guest request cannot be cancelled after registration has been confirmed."), frappe.ValidationError)
	if doc.linked_appointment and frappe.db.exists("Veterinary Appointment", doc.linked_appointment):
		appointment = frappe.get_doc("Veterinary Appointment", doc.linked_appointment); appointment.check_permission("write")
		if appointment.status != "Awaiting Registration": frappe.throw(_("The linked appointment has already progressed and must be handled from Appointments."), frappe.ValidationError)
		previous_status = appointment.status; appointment.status = "Cancelled"; appointment.save(); emit_appointment_status_notification(appointment, previous_status, appointment.status)
	doc.status = "Cancelled"; doc.save()

@frappe.whitelist()
def get_appointment_queue_view(branch: str | None = None, practitioner: str | None = None, status: str | None = None, reference_date: str | None = None) -> dict[str, list[dict]]:
	_require_front_desk_context()
	if status and status not in APPOINTMENT_STATUSES: frappe.throw(_("Invalid appointment status."), frappe.ValidationError)
	day = getdate(reference_date or now_datetime()); base_filters = _branch_filters(branch)
	if practitioner: base_filters["practitioner"] = practitioner
	base_filters["status"] = status if status else ["in", list(ACTIVE_QUEUE_STATUSES)]
	return {"today": _queue_rows({**base_filters, "appointment_datetime": ["between", [f"{day} 00:00:00", f"{day} 23:59:59"]]}), "tomorrow": _queue_rows({**base_filters, "appointment_datetime": ["between", [f"{add_days(day, 1)} 00:00:00", f"{add_days(day, 1)} 23:59:59"]]}), "future": _queue_rows({**base_filters, "appointment_datetime": [">=", f"{add_days(day, 2)} 00:00:00"]})}

def _queue_rows(filters: dict) -> list[dict]:
	return frappe.get_list("Veterinary Appointment", filters=filters, fields=["name", "appointment_title", "patient", "primary_owner", "practitioner", "practitioner_name", "branch", "appointment_datetime", "status", "appointment_type", "linked_consultation", "modified"], order_by="appointment_datetime asc")

@frappe.whitelist()
def get_appointment_action_detail(name: str) -> dict:
	user = _require_front_desk_context(); doc = frappe.get_doc("Veterinary Appointment", name); doc.check_permission("read"); _validate_branch(doc.branch); can_write = bool(doc.has_permission("write")) and user_has_any_role(user, QUEUE_QUICK_ACTION_ROLES); actions = []
	if can_write and doc.status in {"Scheduled", "Rescheduled"}: actions.append({"key": "confirm", "label": _("Confirm"), "primary": True})
	if can_write and doc.status == "Confirmed": actions.append({"key": "check_in", "label": _("Check In"), "primary": True})
	if can_write and doc.status in {"Confirmed", "Checked In"} and not doc.linked_consultation: actions.append({"key": "start_consultation", "label": _("Start Consultation"), "primary": True})
	return {"name": doc.name, "modified": doc.modified, "status": doc.status, "can_write": can_write, "values": {"appointment_title": doc.appointment_title, "patient": doc.patient, "patient_label": _row_title("Veterinary Patient", doc.patient), "primary_owner": doc.primary_owner, "owner_label": _row_title("Customer", doc.primary_owner), "appointment_datetime": doc.appointment_datetime, "practitioner": doc.practitioner, "practitioner_name": doc.practitioner_name, "branch": doc.branch, "appointment_type": doc.appointment_type, "notes": doc.notes, "linked_consultation": doc.linked_consultation}, "actions": actions}

@frappe.whitelist()
def perform_appointment_queue_action(name: str, action: str, modified: str | None = None) -> dict:
	user = _require_front_desk_context(); doc = frappe.get_doc("Veterinary Appointment", name); doc.check_permission("write"); _validate_branch(doc.branch)
	if not user_has_any_role(user, QUEUE_QUICK_ACTION_ROLES): frappe.throw(_("Not permitted to perform appointment queue actions."), frappe.PermissionError)
	_assert_timestamp(doc.doctype, doc.name, modified); require_vetedge_platform_access(action=f"front_desk_appointment_{action}", reference_doctype=doc.doctype, reference_name=doc.name); result = {}
	if action == "confirm":
		if doc.status not in {"Scheduled", "Rescheduled"}: frappe.throw(_("Only Scheduled or Rescheduled appointments can be confirmed."), frappe.ValidationError)
		transition_appointment_status(doc.name, "Confirmed")
	elif action == "check_in":
		if doc.status != "Confirmed": frappe.throw(_("Only Confirmed appointments can be checked in."), frappe.ValidationError)
		transition_appointment_status(doc.name, "Checked In")
	elif action == "start_consultation":
		if doc.status not in {"Confirmed", "Checked In"}: frappe.throw(_("Appointment must be Confirmed or Checked In."), frappe.ValidationError)
		result["consultation"] = create_consultation_from_appointment(doc.name)
	else: frappe.throw(_("Unsupported appointment queue action."), frappe.ValidationError)
	result["detail"] = get_appointment_action_detail(doc.name); return result

@frappe.whitelist()
def get_missed_appointments(search: str = "", status: str | None = None, branch: str | None = None, resolved: str | int | None = None, start: int = 0, page_length: int = 25) -> dict:
	_require_front_desk_context()
	if not frappe.has_permission("Veterinary Missed Appointment", "read"): frappe.throw(_("You are not permitted to view missed appointments."), frappe.PermissionError)
	filters = _branch_filters(branch)
	if status: filters["status"] = status
	if resolved not in (None, ""): filters["resolved"] = cint(resolved)
	query = str(search or "").strip(); or_filters = [["Veterinary Missed Appointment", fieldname, "like", f"%{query}%"] for fieldname in ("name", "appointment", "patient", "primary_owner", "practitioner")] if query else None; start, page_length = _page_values(start, page_length)
	rows = frappe.get_list("Veterinary Missed Appointment", fields=["name", "appointment", "appointment_datetime", "patient", "primary_owner", "branch", "practitioner", "status", "resolved", "contacted", "resolution_status", "modified"], filters=filters, or_filters=or_filters, order_by="appointment_datetime desc", start=start, page_length=page_length)
	return {"rows": rows, "total": _permission_count("Veterinary Missed Appointment", filters, or_filters), "start": start, "page_length": page_length}

@frappe.whitelist()
def get_missed_appointment_detail(name: str) -> dict:
	user = _require_front_desk_context(); doc = frappe.get_doc("Veterinary Missed Appointment", name); doc.check_permission("read"); _validate_branch(doc.branch); can_write = bool(doc.has_permission("write")); actions = []
	if can_write and not cint(doc.resolved): actions.extend([{"key": "mark_contacted", "label": _("Mark Contacted")}, {"key": "reschedule", "label": _("Reschedule"), "primary": True}, {"key": "cancel_appointment", "label": _("Cancel Appointment"), "danger": True}, {"key": "resolve", "label": _("Resolve")}])
	elif can_write and user_has_any_role(user, {*ELEVATED_ROLES, ROLE_BRANCH_MANAGER, "VetEdge Branch Manager"}): actions.append({"key": "reopen", "label": _("Reopen")})
	return {"name": doc.name, "modified": doc.modified, "status": doc.status, "can_write": can_write, "values": {"appointment": doc.appointment, "appointment_datetime": doc.appointment_datetime, "patient": doc.patient, "patient_label": _row_title("Veterinary Patient", doc.patient), "primary_owner": doc.primary_owner, "owner_label": _row_title("Customer", doc.primary_owner), "branch": doc.branch, "practitioner": doc.practitioner, "original_status": doc.original_status, "missed_reason": doc.missed_reason, "contacted": cint(doc.contacted), "contacted_on": doc.contacted_on, "contacted_by": doc.contacted_by, "contact_note": doc.contact_note, "resolved": cint(doc.resolved), "resolution_status": doc.resolution_status, "resolution_note": doc.resolution_note, "resolved_on": doc.resolved_on, "resolved_by": doc.resolved_by}, "actions": actions}

@frappe.whitelist()
def perform_missed_appointment_action(name: str, action: str, modified: str | None = None, values: str | dict | None = None) -> dict:
	_require_front_desk_context(); doc = frappe.get_doc("Veterinary Missed Appointment", name); doc.check_permission("write"); _validate_branch(doc.branch); _assert_timestamp(doc.doctype, doc.name, modified); require_vetedge_platform_access(action=f"front_desk_missed_{action}", reference_doctype=doc.doctype, reference_name=doc.name); payload = _parse_json_object(values)
	if action == "mark_contacted": mark_missed_appointment_contacted(doc.name, note=payload.get("note"))
	elif action == "reschedule": reschedule_missed_appointment(doc.name, new_date=payload.get("new_date"), new_time=payload.get("new_time"), note=payload.get("note"))
	elif action == "cancel_appointment": cancel_missed_appointment(doc.name, note=payload.get("note"))
	elif action == "resolve": resolve_missed_appointment(doc.name, resolution_note=payload.get("resolution_note"))
	elif action == "reopen": reopen_missed_appointment(doc.name, note=payload.get("note"))
	else: frappe.throw(_("Unsupported missed appointment action."), frappe.ValidationError)
	return get_missed_appointment_detail(doc.name)

@frappe.whitelist()
def get_front_desk_link_options(fieldname: str, query: str = "") -> list[dict]:
	_require_front_desk_context(); text = str(query or "").strip()
	if fieldname == "branch":
		filters = {}; user = get_current_user(); assigned = get_assigned_branches(user)
		if assigned and not user_has_global_branch_access(user): filters["name"] = ["in", assigned]
		rows = frappe.get_list("Branch", fields=["name"], filters=filters, or_filters=[["Branch", "name", "like", f"%{text}%"]] if text else None, order_by="name asc", page_length=20); return [{"value": row.name, "label": row.name} for row in rows]
	if fieldname == "practitioner":
		users = frappe.get_all("Has Role", filters={"role": "VetEdge Doctor", "parenttype": "User"}, pluck="parent")
		if not users: return []
		rows = frappe.get_list("User", fields=["name", "full_name"], filters={"name": ["in", users], "enabled": 1}, or_filters=[["User", "name", "like", f"%{text}%"], ["User", "full_name", "like", f"%{text}%"]] if text else None, order_by="full_name asc", page_length=20); return [{"value": row.name, "label": row.full_name or row.name} for row in rows]
	frappe.throw(_("Unsupported Front Desk Link field."), frappe.ValidationError)
