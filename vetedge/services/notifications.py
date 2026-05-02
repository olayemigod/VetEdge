from __future__ import annotations

import json

import frappe
from frappe.utils import escape_html
from frappe.utils import add_to_date, now_datetime

from vetedge.services.branding import get_clinic_brand_name
from vetedge.services.notification_events import get_notification_event_definition


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
	"lab_order_created",
	"lab_sample_collected",
	"lab_result_entered",
	"lab_result_ready_for_review",
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

LAB_NOTIFICATION_ROLES = {
	"Lab Technician",
	"VetEdge Doctor",
	"VetEdge Administrator",
	"Branch Manager",
}

LAB_REVIEW_NOTIFICATION_ROLES = {
	"VetEdge Doctor",
	"VetEdge Administrator",
	"Branch Manager",
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
	"lab_order_created": "notify_on_lab_updates",
	"lab_sample_collected": "notify_on_lab_updates",
	"lab_result_entered": "notify_on_lab_updates",
	"lab_result_ready_for_review": "notify_on_lab_updates",
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
		"backend_mode": settings.get("notification_backend_mode", "local"),
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
			for recipient in recipients:
				log_notification_attempt(
					event_payload=event_payload,
					channel="Email",
					recipient=recipient,
					status="Queued",
					settings=settings,
				)
		else:
			delivery["Email"] = {"queued": False, "reason": "no_recipients", "recipients": []}
			log_notification_attempt(
				event_payload=event_payload,
				channel="Email",
				recipient=None,
				status="Skipped",
				error_message="No recipients resolved for the notification event.",
				settings=settings,
			)

	for channel in settings.get("channels", []):
		if channel != "Email":
			delivery[channel] = {"queued": False, "reason": "provider_not_configured"}
			log_notification_attempt(
				event_payload=event_payload,
				channel=channel,
				recipient=None,
				status="Skipped",
				error_message="Provider routing is not configured yet for this channel.",
				settings=settings,
			)

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
	if event in {"accounts_action_required", "consultation_awaiting_payment"}:
		roles = ACCOUNTS_NOTIFICATION_ROLES
	elif event == "lab_result_ready_for_review":
		roles = LAB_REVIEW_NOTIFICATION_ROLES
	elif event in {"lab_order_created", "lab_sample_collected", "lab_result_entered"}:
		roles = LAB_NOTIFICATION_ROLES
	else:
		roles = STAFF_NOTIFICATION_ROLES
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
	channels = resolve_notification_channels(settings, meta)

	result = {
		"enabled": enabled,
		"channels": channels,
		"enable_email_notifications": "Email" in channels,
		"enable_sms_notifications": "SMS" in channels,
		"enable_whatsapp_notifications": "WhatsApp" in channels,
		"notification_backend_mode": settings.get("notification_backend_mode")
		if meta.has_field("notification_backend_mode")
		else "local",
		"processedge_core_notifications_enabled": settings.get("processedge_core_notifications_enabled")
		if meta.has_field("processedge_core_notifications_enabled")
		else 0,
		"processedge_core_notification_endpoint": settings.get("processedge_core_notification_endpoint")
		if meta.has_field("processedge_core_notification_endpoint")
		else None,
		"processedge_core_notification_api_key": settings.get("processedge_core_notification_api_key")
		if meta.has_field("processedge_core_notification_api_key")
		else None,
		"appointment_reminder_hours": settings.get("appointment_reminder_hours")
		if meta.has_field("appointment_reminder_hours")
		else settings.get("appointment_reminder_hours_before")
		if meta.has_field("appointment_reminder_hours_before")
		else 24,
		"appointment_reminder_hours_before": 24,
		"vaccination_due_reminder_days": settings.get("vaccination_due_reminder_days")
		if meta.has_field("vaccination_due_reminder_days")
		else 7,
		"payment_reminder_days": settings.get("payment_reminder_days")
		if meta.has_field("payment_reminder_days")
		else 3,
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
		"notify_on_lab_updates": False,
	}

	for fieldname in result:
		if fieldname in {"enabled", "channels"}:
			continue
		if meta.has_field(fieldname):
			result[fieldname] = settings.get(fieldname)

	if meta.has_field("appointment_reminder_hours") and result.get("appointment_reminder_hours"):
		result["appointment_reminder_hours_before"] = result["appointment_reminder_hours"]

	return result


def default_notification_settings() -> dict:
	return {
		"enabled": False,
		"channels": [],
		"enable_email_notifications": False,
		"enable_sms_notifications": False,
		"enable_whatsapp_notifications": False,
		"notification_backend_mode": "local",
		"processedge_core_notifications_enabled": 0,
		"processedge_core_notification_endpoint": None,
		"processedge_core_notification_api_key": None,
		"appointment_reminder_hours": 24,
		"appointment_reminder_hours_before": 24,
		"vaccination_due_reminder_days": 7,
		"payment_reminder_days": 3,
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
		"notify_on_lab_updates": False,
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


def resolve_notification_channels(settings, meta) -> list[str]:
	channels = []
	for fieldname, channel in (
		("enable_email_notifications", "Email"),
		("enable_sms_notifications", "SMS"),
		("enable_whatsapp_notifications", "WhatsApp"),
	):
		if meta.has_field(fieldname) and settings.get(fieldname):
			channels.append(channel)
	if channels:
		return channels

	return parse_notification_channels(
		settings.get("notification_channels") if meta.has_field("notification_channels") else None
	)


def log_notification_attempt(
	event_payload: dict,
	channel: str,
	recipient: str | None,
	status: str,
	settings: dict | None = None,
	error_message: str | None = None,
) -> None:
	try:
		if not frappe.db.exists("DocType", "VetEdge Notification Log"):
			return
		event_definition = get_notification_event_definition(event_payload["event"])
		doc = frappe.get_doc(
			{
				"doctype": "VetEdge Notification Log",
				"event_key": event_payload["event"],
				"channel": channel,
				"recipient": recipient,
				"audience_type": event_definition.audience if event_definition else None,
				"reference_doctype": event_payload.get("reference_doctype"),
				"reference_name": event_payload.get("reference_name"),
				"status": status,
				"backend_mode": (settings or {}).get("notification_backend_mode")
				or event_payload.get("backend_mode")
				or "local",
				"error_message": error_message,
				"created_on": now_datetime(),
				"sent_on": now_datetime() if status == "Sent" else None,
				"payload_preview": build_payload_preview(event_payload.get("payload") or {}),
			}
		)
		doc.insert(ignore_permissions=True)
	except Exception:
		pass


def build_payload_preview(payload: dict) -> str:
	if not payload:
		return ""

	preview = {}
	for key, value in payload.items():
		if any(marker in key.lower() for marker in ("note", "notes", "medical", "diagnosis")):
			continue
		preview[key] = value
	return json.dumps(preview, default=str, ensure_ascii=True)[:1400]


def is_event_enabled(event: str, settings: dict) -> bool:
	setting_field = EVENT_SETTING_FIELDS.get(event)
	if not setting_field:
		return True

	return bool(settings.get(setting_field))


def send_due_appointment_reminders() -> list[dict]:
	settings = get_notification_settings()
	if not settings["enabled"] or not settings.get("notify_on_appointment_reminder"):
		return []

	cutoff = add_to_date(
		now_datetime(), hours=int(settings.get("appointment_reminder_hours") or settings.get("appointment_reminder_hours_before") or 24)
	)
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
