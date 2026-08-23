from __future__ import annotations

from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import cstr

from vetedge.services.permissions import can_access_branch_data, get_current_user
from vetedge.services.portal_access import require_internal_user


CONSULTATION_APPOINTMENT_TYPES = {"Consultation", "Follow Up"}
READ_ONLY_ACTIONS = {
	"open_registration",
	"open_consultation",
	"open_grooming_session",
	"vaccination_workflow",
	"boarding_operations",
}


def normalize_appointment_type(doc) -> str:
	"""Treat old blank appointment types as Consultation without rewriting history."""
	return cstr(doc.get("appointment_type") or "").strip() or "Consultation"


def _action(key: str, label: str, *, primary: bool = False, danger: bool = False, navigation: bool = False) -> dict:
	return {
		"key": key,
		"label": _(label),
		"primary": primary,
		"danger": danger,
		"navigation": navigation,
		"mutates": key not in READ_ONLY_ACTIONS,
	}


def _existing_grooming_session(appointment: str) -> str | None:
	if not frappe.db.exists("DocType", "Pet Grooming Session"):
		return None
	if not frappe.has_permission("Pet Grooming Session", "read"):
		return None
	rows = frappe.get_list(
		"Pet Grooming Session",
		filters={"veterinary_appointment": appointment},
		fields=["name"],
		order_by="creation desc",
		page_length=1,
	)
	return rows[0].name if rows else None


def _vaccination_route(doc) -> str:
	params = [
		"resource=vaccinations",
		"new=1",
		f"patient={quote(cstr(doc.get('patient') or ''))}",
		f"service_branch={quote(cstr(doc.get('branch') or ''))}",
	]
	return "/desk/vetedge-resource-center?" + "&".join(params)


def _boarding_route(doc) -> str:
	patient = quote(cstr(doc.get("patient") or ""))
	return f"/desk/vetedge-service-operations?resource=boarding-bookings&search={patient}" if patient else "/desk/vetedge-service-operations?resource=boarding-bookings"


def _consultation_route(name: str) -> str:
	return f"/desk/vetedge-clinical-workspace?consultation={quote(cstr(name))}"


def _grooming_route(name: str) -> str:
	return f"/desk/vetedge-service-operations?resource=grooming-sessions&name={quote(cstr(name))}"


def build_appointment_action_state(doc) -> dict:
	appointment_type = normalize_appointment_type(doc)
	status = cstr(doc.get("status") or "").strip()
	can_write = bool(doc.has_permission("write"))
	linked_consultation = cstr(doc.get("linked_consultation") or "").strip()
	grooming_session = _existing_grooming_session(doc.name) if appointment_type == "Grooming" else None
	actions: list[dict] = []
	message = ""

	if status == "Awaiting Registration":
		if doc.get("guest_booking_request"):
			actions.append(_action("open_registration", "Open Registration Request", navigation=True, primary=True))
		message = _("Complete registration before progressing this appointment.")
	elif status == "Owner Requested" and can_write:
		actions.extend(
		[
			_action("approve", "Approve Appointment", primary=True),
			_action("cancel_request", "Cancel Request", danger=True),
		]
	)
	elif status in {"Scheduled", "Rescheduled"} and can_write:
		actions.append(_action("confirm", "Confirm Appointment", primary=True))
	elif status == "Confirmed" and can_write:
		actions.append(_action("check_in", "Check In", primary=True))

	if linked_consultation:
		actions.append(_action("open_consultation", "Open Consultation", navigation=True, primary=status in {"In Consultation", "Completed"}))
	elif appointment_type in CONSULTATION_APPOINTMENT_TYPES and can_write and status in {"Confirmed", "Checked In"}:
		label = "Start Follow-up Consultation" if appointment_type == "Follow Up" else "Start Consultation"
		actions.append(_action("start_consultation", label, primary=status == "Checked In"))

	if appointment_type == "Grooming":
		if grooming_session:
			actions.append(_action("open_grooming_session", "Open Grooming Session", navigation=True, primary=status in {"Checked In", "In Service", "Completed"}))
		elif can_write and status in {"Confirmed", "Checked In", "In Service"}:
			actions.append(_action("start_grooming_session", "Create Grooming Session", primary=status in {"Checked In", "In Service"}))
		if status == "Checked In":
			message = _("Continue this appointment in the Grooming Session workflow.")

	if appointment_type == "Vaccination" and status in {"Confirmed", "Checked In"}:
		actions.append(_action("vaccination_workflow", "Open Vaccination Workflow", navigation=True, primary=status == "Checked In"))
		if status == "Checked In":
			message = _("Continue in Vaccination. Billing, payment, stock, batch and administration rules remain authoritative there.")

	if appointment_type == "Boarding":
		actions.append(_action("boarding_operations", "Open Boarding Operations", navigation=True, primary=status == "Checked In"))
		message = _("Boarding reservations and service delivery are managed from Boarding Bookings and Boarding Stays.")

	if appointment_type == "Other" and status == "Checked In":
		message = _("This is an Other appointment. VetEdge will not assume a Consultation, Vaccination, Grooming or Boarding workflow.")

	return {
		"appointment": doc.name,
		"appointment_type": appointment_type,
		"status": status,
		"can_write": can_write,
		"message": message,
		"actions": actions,
		"linked_consultation": linked_consultation or None,
		"grooming_session": grooming_session,
	}


@frappe.whitelist()
def get_appointment_action_state(appointment: str) -> dict:
	require_internal_user()
	doc = frappe.get_doc("Veterinary Appointment", appointment)
	doc.check_permission("read")
	if doc.get("branch"):
		can_access_branch_data(get_current_user(), doc.branch, raise_exception=True)
	return build_appointment_action_state(doc)


def _assert_not_stale(doc, expected_modified: str | None = None) -> None:
	if not expected_modified:
		return
	current = frappe.db.get_value(doc.doctype, doc.name, "modified")
	if current and cstr(current) != cstr(expected_modified):
		raise frappe.TimestampMismatchError(
		_("This appointment changed after it was opened. Refresh and try again.")
	)


def _open_result(*, route: str, message: str, state: dict | None = None) -> dict:
	return {"mutated": False, "message": _(message), "open": {"route": route}, "state": state}


@frappe.whitelist()
def perform_appointment_action(appointment: str, action: str, expected_modified: str | None = None) -> dict:
	require_internal_user()
	doc = frappe.get_doc("Veterinary Appointment", appointment)
	doc.check_permission("read")
	if doc.get("branch"):
		can_access_branch_data(get_current_user(), doc.branch, raise_exception=True)
	_assert_not_stale(doc, expected_modified)

	state = build_appointment_action_state(doc)
	allowed = {row.get("key") for row in state.get("actions") or []}
	if action not in allowed:
		frappe.throw(_("This action is no longer valid for the appointment type or status. Refresh the appointment and try again."), frappe.ValidationError)

	if action == "open_registration":
		return _open_result(
			route=f"/desk/veterinary-guest-booking-request/{quote(cstr(doc.guest_booking_request))}",
			message="Opening registration request.",
			state=state,
		)
	if action == "open_consultation":
		return _open_result(route=_consultation_route(doc.linked_consultation), message="Opening consultation.", state=state)
	if action == "open_grooming_session":
		return _open_result(route=_grooming_route(state.get("grooming_session")), message="Opening grooming session.", state=state)
	if action == "vaccination_workflow":
		return _open_result(route=_vaccination_route(doc), message="Opening vaccination workflow.", state=state)
	if action == "boarding_operations":
		return _open_result(route=_boarding_route(doc), message="Opening boarding operations.", state=state)

	doc.check_permission("write")
	from vetedge.services.platform_access import require_vetedge_platform_access

	require_vetedge_platform_access(
		action=f"appointment_{action}",
		reference_doctype=doc.doctype,
		reference_name=doc.name,
	)

	if action in {"approve", "cancel_request", "confirm", "check_in"}:
		from vetedge.services.appointment_flow import transition_appointment_status

		target = {
			"approve": "Scheduled",
			"cancel_request": "Cancelled",
			"confirm": "Confirmed",
			"check_in": "Checked In",
		}[action]
		transition_appointment_status(doc.name, target)
		doc.reload()
		return {
			"mutated": True,
			"message": _("Appointment updated."),
			"open": None,
			"state": build_appointment_action_state(doc),
		}

	if action == "start_consultation":
		if normalize_appointment_type(doc) not in CONSULTATION_APPOINTMENT_TYPES:
			frappe.throw(_("Only Consultation and Follow Up appointments can start a Veterinary Consultation."), frappe.ValidationError)
		from vetedge.services.appointment_flow import create_consultation_from_appointment

		result = create_consultation_from_appointment(doc.name)
		return {
			"mutated": True,
			"message": _("Consultation started."),
			"open": {"route": _consultation_route(result.get("name"))},
			"state": None,
		}

	if action == "start_grooming_session":
		if normalize_appointment_type(doc) != "Grooming":
			frappe.throw(_("Only Grooming appointments can create Grooming Sessions."), frappe.ValidationError)
		from vetedge.services.appointment_grooming_bridge import create_grooming_session_from_veterinary_appointment

		result = create_grooming_session_from_veterinary_appointment(doc.name)
		return {
			"mutated": bool(result.get("created")),
			"message": _("Grooming session is ready."),
			"open": {"route": _grooming_route(result.get("name"))},
			"state": None,
		}

	frappe.throw(_("Unsupported appointment action."), frappe.ValidationError)
