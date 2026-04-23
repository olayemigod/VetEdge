from __future__ import annotations

import frappe
from frappe.utils import escape_html
from frappe.utils import add_to_date, now_datetime

from vetedge.services.branding import get_clinic_brand_name


SUPPORTED_CHANNELS = {"Email", "SMS", "WhatsApp"}

OWNER_EVENTS = {
	"appointment_created",
	"appointment_booked",
	"appointment_scheduled",
	"appointment_confirmed",
	"appointment_checked_in",
	"appointment_reminder",
	"appointment_rescheduled",
	"appointment_cancelled",
	"appointment_completed",
	"registration_confirmed",
	"invoice_created",
	"payment_received",
	"payment_initiated",
	"payment_reminder",
}

STAFF_EVENTS = {
	"owner_appointment_request_received",
	"guest_appointment_request_received",
	"guest_appointment_ready_for_approval",
	"registration_request_received",
	"accounts_action_required",
	"consultation_awaiting_payment",
	"consultation_sent_to_dispensary",
	"dispensary_confirmation_completed",
	"dispensary_stock_issue_failed",
	"dispensary_expired_stock_blocked",
	"dispensary_insufficient_non_expired_stock",
	"consultation_ready_for_treatment",
}

STAFF_NOTIFICATION_ROLES = {
	"System Manager",
	"VetEdge Administrator",
	"VetEdge Front Desk",
}

ACCOUNTS_NOTIFICATION_ROLES = {
	"Accounts Manager",
	"Accounts User",
	"VetEdge Administrator",
}

EVENT_SETTING_FIELDS = {
	"appointment_created": "notify_on_appointment_create",
	"appointment_booked": "notify_on_appointment_create",
	"appointment_scheduled": "notify_on_appointment_status_change",
	"appointment_confirmed": "notify_on_appointment_status_change",
	"appointment_checked_in": "notify_on_appointment_status_change",
	"appointment_started": "notify_on_appointment_status_change",
	"appointment_completed": "notify_on_appointment_status_change",
	"appointment_no_show": "notify_on_appointment_status_change",
	"appointment_reminder": "notify_on_appointment_reminder",
	"appointment_rescheduled": "notify_on_reschedule",
	"appointment_cancelled": "notify_on_cancellation",
	"owner_appointment_request_received": "notify_on_owner_portal_appointment_request",
	"guest_appointment_request_received": "notify_on_guest_appointment_request",
	"guest_appointment_ready_for_approval": "notify_on_guest_appointment_request",
	"registration_request_received": "notify_on_guest_registration_request",
	"registration_confirmed": "notify_on_guest_registration_confirmed",
	"invoice_created": "notify_on_invoice_created",
	"payment_received": "notify_on_payment_received",
	"payment_reminder": "notify_on_payment_received",
	"accounts_action_required": "notify_on_accounts_action_required",
	"consultation_awaiting_payment": "notify_on_accounts_action_required",
	"consultation_sent_to_dispensary": "notify_on_accounts_action_required",
	"dispensary_confirmation_completed": "notify_on_payment_received",
	"dispensary_stock_issue_failed": "notify_on_accounts_action_required",
	"dispensary_expired_stock_blocked": "notify_on_accounts_action_required",
	"dispensary_insufficient_non_expired_stock": "notify_on_accounts_action_required",
	"consultation_ready_for_treatment": "notify_on_payment_received",
}

APPOINTMENT_EVENTS = {
	"appointment_created",
	"appointment_booked",
	"appointment_scheduled",
	"appointment_confirmed",
	"appointment_checked_in",
	"appointment_started",
	"appointment_completed",
	"appointment_no_show",
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
	delivery = dispatch_notification_event(event_payload, settings)
	frappe.logger("vetedge.notifications").info(event_payload)
	return {"queued": True, "delivery": delivery, **event_payload}


def dispatch_notification_event(event_payload: dict, settings: dict | None = None) -> dict:
	settings = settings or get_notification_settings()
	delivery = {"Email": {"queued": False, "recipients": []}}

	if "Email" in settings.get("channels", []):
		recipients = get_email_recipients(event_payload["event"], event_payload.get("payload") or {})
		if recipients:
			frappe.sendmail(
				recipients=recipients,
				subject=get_email_subject(event_payload),
				message=get_email_message(event_payload),
				delayed=True,
				reference_doctype=event_payload["reference_doctype"],
				reference_name=event_payload["reference_name"],
			)
			delivery["Email"] = {"queued": True, "recipients": recipients}
		else:
			delivery["Email"] = {"queued": False, "reason": "no_recipients", "recipients": []}

	for channel in settings.get("channels", []):
		if channel != "Email":
			delivery[channel] = {"queued": False, "reason": "provider_not_configured"}

	return delivery


def get_email_recipients(event: str, payload: dict) -> list[str]:
	recipients: set[str] = set()

	if event in OWNER_EVENTS:
		recipients.update(get_owner_email_recipients(payload))

	if event in STAFF_EVENTS:
		recipients.update(get_staff_email_recipients(event))

	if payload.get("email"):
		recipients.add(payload["email"])
	if payload.get("guest_email"):
		recipients.add(payload["guest_email"])

	return sorted(email for email in recipients if email)


def get_owner_email_recipients(payload: dict) -> set[str]:
	recipients: set[str] = set()
	customer = payload.get("customer") or payload.get("primary_owner")
	patient = payload.get("patient")

	if not customer and patient:
		customer = frappe.db.get_value("Veterinary Patient", patient, "primary_owner")

	if not customer and payload.get("invoice"):
		customer = frappe.db.get_value("Sales Invoice", payload["invoice"], "customer")

	if not customer:
		return recipients

	customer_email = frappe.db.get_value("Customer", customer, "email_id")
	if customer_email:
		recipients.add(customer_email)

	if frappe.db.exists("DocType", "Portal User"):
		recipients.update(
			frappe.get_all(
				"Portal User",
				filters={"parenttype": "Customer", "parent": customer},
				pluck="user",
			)
		)

	return recipients


def get_staff_email_recipients(event: str) -> set[str]:
	roles = ACCOUNTS_NOTIFICATION_ROLES if event in {"accounts_action_required", "consultation_awaiting_payment"} else STAFF_NOTIFICATION_ROLES
	users = frappe.get_all(
		"Has Role",
		filters={"role": ["in", list(roles)], "parenttype": "User"},
		pluck="parent",
	)
	if not users:
		return set()

	enabled_users = frappe.get_all(
		"User",
		filters={"name": ["in", users], "enabled": 1},
		pluck="email",
	)
	return set(enabled_users)


def get_email_subject(event_payload: dict) -> str:
	event_label = event_payload["event"].replace("_", " ").title()
	return f"{get_clinic_brand_name()}: {event_label}"


def get_email_message(event_payload: dict) -> str:
	brand_name = get_clinic_brand_name()
	payload = event_payload.get("payload") or {}
	rows = [
		("Event", event_payload["event"].replace("_", " ").title()),
		("Reference", f"{event_payload['reference_doctype']} {event_payload['reference_name']}"),
	]
	for key, value in payload.items():
		if value in (None, ""):
			continue
		rows.append((key.replace("_", " ").title(), value))

	items = "".join(
		f"<tr><th style='text-align:left;padding:6px;border:1px solid #ddd'>{escape_html(str(label))}</th>"
		f"<td style='padding:6px;border:1px solid #ddd'>{escape_html(str(value))}</td></tr>"
		for label, value in rows
	)
	return f"<p>An update is available from {escape_html(brand_name)}.</p><table style='border-collapse:collapse'>{items}</table>"


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
		"notify_on_appointment_status_change": False,
		"notify_on_appointment_reminder": False,
		"notify_on_reschedule": False,
		"notify_on_cancellation": False,
		"notify_on_owner_portal_appointment_request": False,
		"notify_on_guest_registration_request": False,
		"notify_on_guest_registration_confirmed": False,
		"notify_on_guest_appointment_request": False,
		"notify_on_invoice_created": False,
		"notify_on_payment_received": False,
		"notify_on_accounts_action_required": False,
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
		"notify_on_appointment_status_change": False,
		"notify_on_appointment_reminder": False,
		"notify_on_reschedule": False,
		"notify_on_cancellation": False,
		"notify_on_owner_portal_appointment_request": False,
		"notify_on_guest_registration_request": False,
		"notify_on_guest_registration_confirmed": False,
		"notify_on_guest_appointment_request": False,
		"notify_on_invoice_created": False,
		"notify_on_payment_received": False,
		"notify_on_accounts_action_required": False,
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
