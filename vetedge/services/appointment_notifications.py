from __future__ import annotations

import frappe
from frappe.utils import add_to_date, cstr, get_datetime, now_datetime

from vetedge.services.notifications import (
	create_notification_item,
	get_role_recipients,
	get_user_recipient,
)


APPOINTMENT_DOCTYPE = "Veterinary Appointment"
TERMINAL_APPOINTMENT_STATUSES = {"Completed", "Cancelled", "No Show"}
MISSED_APPOINTMENT_STATUSES = {"Awaiting Registration", "Owner Requested", "Scheduled"}
DUE_SOON_STATUSES = {"Scheduled", "Confirmed"}
WAITING_STATUSES = {"Checked In"}
DEFAULT_DUE_SOON_WINDOW_MINUTES = 60
DEFAULT_WAITING_THRESHOLD_MINUTES = 30
HIGH_VISIBILITY_ROLES = {
	"VetEdge Front Desk",
	"Branch Manager",
	"VetEdge Branch Manager",
	"VetEdge Administrator",
}

APPOINTMENT_NOTIFICATION_CONFIG = {
	"appointment_due_soon": {
		"title": "Veterinary appointment due soon",
		"category": "Appointment",
		"priority": "Normal",
	},
	"missed_appointment": {
		"title": "Veterinary appointment missed",
		"category": "Appointment",
		"priority": "High",
	},
	"appointment_checked_in": {
		"title": "Veterinary appointment checked in",
		"category": "Appointment",
		"priority": "Normal",
	},
	"appointment_waiting_too_long": {
		"title": "Veterinary appointment waiting too long",
		"category": "Appointment",
		"priority": "High",
	},
	"appointment_completed": {
		"title": "Veterinary appointment completed",
		"category": "Appointment",
		"priority": "Normal",
	},
	"appointment_reminder_sent": {
		"title": "Veterinary appointment reminder sent",
		"category": "Reminder",
		"priority": "Low",
	},
	"appointment_reminder_failed": {
		"title": "Veterinary appointment reminder failed",
		"category": "Reminder",
		"priority": "High",
	},
}


def notify_appointment_due_soon(appointment, window_minutes: int = DEFAULT_DUE_SOON_WINDOW_MINUTES) -> list[dict]:
	return create_appointment_notifications(
		"appointment_due_soon",
		appointment,
		window_minutes=window_minutes,
	)


def notify_missed_appointment(appointment) -> list[dict]:
	return create_appointment_notifications("missed_appointment", appointment)


def notify_appointment_checked_in(appointment) -> list[dict]:
	return create_appointment_notifications("appointment_checked_in", appointment)


def notify_appointment_waiting_too_long(
	appointment,
	threshold_minutes: int = DEFAULT_WAITING_THRESHOLD_MINUTES,
) -> list[dict]:
	return create_appointment_notifications(
		"appointment_waiting_too_long",
		appointment,
		threshold_minutes=threshold_minutes,
	)


def notify_appointment_completed(appointment) -> list[dict]:
	return create_appointment_notifications("appointment_completed", appointment)


def notify_appointment_reminder_sent(appointment) -> list[dict]:
	return create_appointment_notifications("appointment_reminder_sent", appointment)


def notify_appointment_reminder_failed(appointment, reason: str | None = None) -> list[dict]:
	return create_appointment_notifications("appointment_reminder_failed", appointment, failure_reason=reason)


def create_appointment_notifications(event_key: str, appointment, **kwargs) -> list[dict]:
	config = APPOINTMENT_NOTIFICATION_CONFIG.get(event_key)
	if not config:
		return []

	results = []
	try:
		recipients = resolve_appointment_notification_recipients(appointment, event_key)
		for recipient_user in recipients:
			results.append(
				create_notification_item(
					event_key=event_key,
					recipient_user=recipient_user,
					notification_title=config["title"],
					message=build_appointment_notification_message(event_key, appointment, **kwargs),
					reference_doctype=APPOINTMENT_DOCTYPE,
					reference_name=appointment.get("name"),
					action_url=get_appointment_action_url(appointment),
					priority=config["priority"],
					payload={
						"category": config["category"],
						"appointment": appointment.get("name"),
						"patient": appointment.get("patient"),
						"branch": appointment.get("branch"),
						"practitioner": appointment.get("practitioner"),
						"appointment_datetime": appointment.get("appointment_datetime"),
						"status": appointment.get("status"),
						**kwargs,
					},
					idempotency_key=build_appointment_notification_idempotency_key(
						event_key,
						appointment,
						recipient_user,
						**kwargs,
					),
				)
			)
	except Exception:
		_log_appointment_notification_error(event_key, appointment)
	return results


def resolve_appointment_notification_recipients(appointment, event_key: str) -> list[str]:
	recipients = []
	for user in (appointment.get("practitioner"), appointment.get("owner"), appointment.get("created_by")):
		recipient = get_user_recipient(user, audience_type="Appointment")
		if recipient:
			recipients.append(recipient["user"])

	if event_key in {"missed_appointment", "appointment_waiting_too_long", "appointment_reminder_failed"}:
		for recipient in get_role_recipients(
			HIGH_VISIBILITY_ROLES,
			branch=appointment.get("branch"),
			audience_type="Appointment Escalation",
		):
			if recipient.get("user"):
				recipients.append(recipient["user"])

	return _dedupe_users(recipients)


def build_appointment_notification_message(event_key: str, appointment, **kwargs) -> str:
	appointment_name = appointment.get("name")
	appointment_time = appointment.get("appointment_datetime")
	patient = appointment.get("patient")
	if event_key == "appointment_due_soon":
		return f"Veterinary appointment {appointment_name} is due within {kwargs.get('window_minutes')} minutes."
	if event_key == "missed_appointment":
		return f"Veterinary appointment {appointment_name} has passed without completion or cancellation."
	if event_key == "appointment_checked_in":
		return f"Veterinary appointment {appointment_name} has checked in."
	if event_key == "appointment_waiting_too_long":
		return f"Veterinary appointment {appointment_name} has been waiting for more than {kwargs.get('threshold_minutes')} minutes."
	if event_key == "appointment_completed":
		return f"Veterinary appointment {appointment_name} has been completed."
	if event_key == "appointment_reminder_sent":
		return f"Veterinary appointment reminder was sent for {appointment_name}."
	if event_key == "appointment_reminder_failed":
		reason = cstr(kwargs.get("failure_reason")).strip()
		return f"Veterinary appointment reminder failed for {appointment_name}.{(' ' + reason) if reason else ''}"
	return f"Veterinary appointment {appointment_name} notification for {patient or appointment_time or 'appointment'}."


def build_appointment_notification_idempotency_key(
	event_key: str,
	appointment,
	recipient_user: str,
	**kwargs,
) -> str:
	parts = [event_key, cstr(appointment.get("name")), cstr(recipient_user)]
	if event_key == "appointment_due_soon":
		parts.insert(2, cstr(kwargs.get("window_minutes") or DEFAULT_DUE_SOON_WINDOW_MINUTES))
	if event_key == "appointment_waiting_too_long":
		parts.insert(2, cstr(kwargs.get("threshold_minutes") or DEFAULT_WAITING_THRESHOLD_MINUTES))
	return "::".join(parts)


def get_appointment_action_url(appointment) -> str | None:
	if not appointment.get("name"):
		return None
	return f"/app/veterinary-appointment/{appointment.get('name')}"


def run_appointment_notification_checks() -> dict:
	return {
		"appointment_due_soon": send_due_soon_appointment_notifications(),
		"missed_appointment": send_missed_appointment_notifications(),
	}


def send_due_soon_appointment_notifications(
	window_minutes: int = DEFAULT_DUE_SOON_WINDOW_MINUTES,
	limit: int = 100,
) -> list[dict]:
	if not _appointment_notifications_available():
		return []

	cutoff = add_to_date(now_datetime(), minutes=window_minutes)
	rows = frappe.get_all(
		APPOINTMENT_DOCTYPE,
		filters={
			"appointment_datetime": ["between", [now_datetime(), cutoff]],
			"status": ["in", sorted(DUE_SOON_STATUSES)],
		},
		fields=_appointment_notification_fields(),
		order_by="appointment_datetime asc",
		limit_page_length=limit,
	)
	results = []
	for row in rows:
		if row.get("status") in TERMINAL_APPOINTMENT_STATUSES:
			continue
		results.extend(notify_appointment_due_soon(row, window_minutes=window_minutes))
	return results


def send_missed_appointment_notifications(limit: int = 100) -> list[dict]:
	if not _appointment_notifications_available():
		return []

	rows = frappe.get_all(
		APPOINTMENT_DOCTYPE,
		filters={
			"appointment_datetime": ["<", now_datetime()],
			"status": ["in", sorted(MISSED_APPOINTMENT_STATUSES)],
		},
		fields=_appointment_notification_fields(),
		order_by="appointment_datetime asc",
		limit_page_length=limit,
	)
	results = []
	for row in rows:
		results.extend(notify_missed_appointment(row))
	return results


def send_waiting_too_long_appointment_notifications(
	threshold_minutes: int = DEFAULT_WAITING_THRESHOLD_MINUTES,
	limit: int = 100,
) -> list[dict]:
	"""Optional helper kept out of the scheduler because no check-in timestamp exists yet."""
	if not _appointment_notifications_available():
		return []

	cutoff = add_to_date(now_datetime(), minutes=-threshold_minutes)
	rows = frappe.get_all(
		APPOINTMENT_DOCTYPE,
		filters={
			"appointment_datetime": ["<", cutoff],
			"status": ["in", sorted(WAITING_STATUSES)],
		},
		fields=_appointment_notification_fields(),
		order_by="appointment_datetime asc",
		limit_page_length=limit,
	)
	results = []
	for row in rows:
		results.extend(notify_appointment_waiting_too_long(row, threshold_minutes=threshold_minutes))
	return results


def _appointment_notification_fields() -> list[str]:
	return [
		"name",
		"owner",
		"patient",
		"primary_owner",
		"branch",
		"practitioner",
		"appointment_datetime",
		"status",
		"appointment_type",
	]


def _appointment_notifications_available() -> bool:
	return bool(
		frappe.db.exists("DocType", APPOINTMENT_DOCTYPE)
		and frappe.db.exists("DocType", "Veterinary Notification Item")
	)


def _dedupe_users(users: list[str]) -> list[str]:
	seen = set()
	result = []
	for user in users:
		user = cstr(user).strip()
		if not user or user in seen:
			continue
		seen.add(user)
		result.append(user)
	return result


def _log_appointment_notification_error(event_key: str, appointment) -> None:
	if not getattr(frappe, "log_error", None):
		return
	try:
		frappe.log_error(
			title="Veterinary Appointment Notification Failed",
			message=f"Could not create {event_key} notification for {appointment.get('name')}.",
		)
	except Exception:
		pass
