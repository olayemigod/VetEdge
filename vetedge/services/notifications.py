from __future__ import annotations

import frappe
from frappe.utils import add_to_date, now_datetime


SUPPORTED_CHANNELS = {"Email", "SMS", "WhatsApp"}

EVENT_SETTING_FIELDS = {
	"appointment_created": "notify_on_appointment_create",
	"appointment_reminder": "notify_on_appointment_reminder",
	"appointment_rescheduled": "notify_on_reschedule",
	"appointment_cancelled": "notify_on_cancellation",
}

APPOINTMENT_EVENTS = {
	"appointment_created",
	"appointment_confirmed",
	"appointment_reminder",
	"appointment_rescheduled",
	"appointment_cancelled",
}


def notify_appointment_event(appointment, event: str) -> dict:
	if event not in APPOINTMENT_EVENTS:
		frappe.throw(f"Unsupported appointment notification event: {event}", frappe.ValidationError)

	return emit_notification_event(
		event=event,
		reference_doctype="Veterinary Appointment",
		reference_name=appointment.name,
		payload={
			"patient": appointment.patient,
			"primary_owner": appointment.primary_owner,
			"branch": appointment.branch,
			"practitioner": appointment.practitioner,
			"appointment_datetime": appointment.appointment_datetime,
			"status": appointment.status,
		},
	)


def emit_notification_event(
	event: str,
	reference_doctype: str,
	reference_name: str,
	payload: dict | None = None,
) -> dict:
	settings = get_notification_settings()
	if not settings["enabled"]:
		return {"queued": False, "reason": "notifications_disabled"}

	if not is_event_enabled(event, settings):
		return {"queued": False, "reason": "event_disabled"}

	if not settings["channels"]:
		return {"queued": False, "reason": "no_channels_configured"}

	event_payload = {
		"event": event,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"channels": settings["channels"],
		"payload": payload or {},
	}
	frappe.logger("vetedge.notifications").info(event_payload)
	return {"queued": True, **event_payload}


def get_notification_settings() -> dict:
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return default_notification_settings()

	settings = frappe.get_single("Veterinary Settings")
	meta = frappe.get_meta("Veterinary Settings")

	enabled = bool(getattr(settings, "enable_vetedge", 0) and getattr(settings, "enable_notifications", 0))
	channels = parse_notification_channels(
		settings.get("notification_channels") if meta.has_field("notification_channels") else None
	)

	result = {
		"enabled": enabled,
		"channels": channels,
		"appointment_reminder_hours_before": 24,
		"notify_on_appointment_create": False,
		"notify_on_appointment_reminder": False,
		"notify_on_reschedule": False,
		"notify_on_cancellation": False,
	}

	for fieldname in result:
		if fieldname in {"enabled", "channels"}:
			continue
		if meta.has_field(fieldname):
			result[fieldname] = settings.get(fieldname)

	return result


def default_notification_settings() -> dict:
	return {
		"enabled": False,
		"channels": [],
		"appointment_reminder_hours_before": 24,
		"notify_on_appointment_create": False,
		"notify_on_appointment_reminder": False,
		"notify_on_reschedule": False,
		"notify_on_cancellation": False,
	}


def parse_notification_channels(value: str | None) -> list[str]:
	if not value:
		return []

	channels = []
	for part in str(value).replace(",", "\n").splitlines():
		channel = part.strip()
		if channel in SUPPORTED_CHANNELS and channel not in channels:
			channels.append(channel)
	return channels


def is_event_enabled(event: str, settings: dict) -> bool:
	setting_field = EVENT_SETTING_FIELDS.get(event)
	if not setting_field:
		return True

	return bool(settings.get(setting_field))


def send_due_appointment_reminders() -> list[dict]:
	settings = get_notification_settings()
	if not settings["enabled"] or not settings.get("notify_on_appointment_reminder"):
		return []

	cutoff = add_to_date(now_datetime(), hours=int(settings.get("appointment_reminder_hours_before") or 24))
	appointments = frappe.get_all(
		"Veterinary Appointment",
		filters={
			"appointment_datetime": ["between", [now_datetime(), cutoff]],
			"status": ["in", ["Scheduled", "Confirmed"]],
			"reminder_sent": 0,
		},
		fields=["name"],
		order_by="appointment_datetime asc",
	)

	results = []
	for row in appointments:
		appointment = frappe.get_doc("Veterinary Appointment", row.name)
		result = notify_appointment_event(appointment, "appointment_reminder")
		results.append(result)
		if result.get("queued"):
			frappe.db.set_value(
				"Veterinary Appointment",
				appointment.name,
				{"reminder_sent": 1, "reminder_sent_on": now_datetime()},
				update_modified=False,
			)

	return results
