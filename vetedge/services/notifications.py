from __future__ import annotations

import json
from hashlib import sha256

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, cstr, flt, getdate, now_datetime, nowdate

from vetedge.services.branding import get_clinic_brand_name
from vetedge.services.notification_backends import get_notification_backend
from vetedge.services.notification_events import (
	get_notification_event_definition,
	get_notification_email_template,
)
from vetedge.services.permissions import get_assigned_branches


SUPPORTED_CHANNELS = {"Email", "SMS", "WhatsApp"}
NOTIFICATION_ITEM_DOCTYPE = "Veterinary Notification Item"
NOTIFICATION_ITEM_STATUSES = {"Unread", "Read", "Acknowledged", "Done", "Dismissed", "Archived"}
NOTIFICATION_ITEM_STATUS_TIMESTAMPS = {
	"Read": "read_on",
	"Acknowledged": "acknowledged_on",
	"Done": "completed_on",
	"Dismissed": "dismissed_on",
	"Archived": "archived_on",
}

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
	"consultation_invoice_created",
	"payment_received",
	"payment_initiated",
	"payment_pending",
	"payment_reminder",
	"vaccination_administered",
	"vaccination_due_soon",
	"vaccination_overdue",
	"grooming_appointment_created",
	"grooming_appointment_confirmed",
	"grooming_completed",
	"boarding_reserved",
	"boarding_checked_in",
	"boarding_checked_out",
	"boarding_invoice_created",
	"invoice_pdf_available",
}

STAFF_NOTIFICATION_ROLES = {
	"System Manager",
	"VetEdge Administrator",
	"VetEdge Front Desk",
}

ACCOUNTS_NOTIFICATION_ROLES = {
	"Accounts Manager",
	"Accounts User",
	"Accounts/Cashier",
	"VetEdge Accounts/Cashier",
	"VetEdge Administrator",
}

LAB_NOTIFICATION_ROLES = {
	"Lab Technician",
	"VetEdge Lab Technician",
	"VetEdge Doctor",
	"VetEdge Administrator",
	"Branch Manager",
	"VetEdge Branch Manager",
}

LAB_REVIEW_NOTIFICATION_ROLES = {
	"VetEdge Doctor",
	"VetEdge Administrator",
	"Branch Manager",
	"VetEdge Branch Manager",
}

DISPENSARY_NOTIFICATION_ROLES = {
	"Dispensary User",
	"VetEdge Dispensary User",
	"VetEdge Administrator",
	"Branch Manager",
	"VetEdge Branch Manager",
}

BOARDING_NOTIFICATION_ROLES = {
	"VetEdge Front Desk",
	"Branch Manager",
	"VetEdge Branch Manager",
	"VetEdge Administrator",
}

GROOMING_NOTIFICATION_ROLES = {
	"VetEdge Groomer",
	"VetEdge Front Desk",
	"Branch Manager",
	"VetEdge Branch Manager",
	"VetEdge Administrator",
}

SYSTEM_NOTIFICATION_USERS = {"Guest", "Administrator"}

ADMIN_ESCALATION_EVENTS = {
	"role_bundle_applied",
	"unauthorized_action_blocked",
	"branch_access_blocked",
	"patient_access_blocked",
	"owner_patient_access_blocked",
	"owner_consultation_access_blocked",
	"medical_history_access_blocked",
	"lab_order_access_blocked",
	"invoice_access_blocked",
	"internal_payment_access_blocked",
	"dispensary_access_blocked",
	"lab_request_blocked",
	"lab_result_entry_blocked",
	"lab_result_review_blocked",
	"grooming_appointment_access_blocked",
	"grooming_session_create_blocked",
	"grooming_session_progress_blocked",
	"grooming_billing_blocked",
	"role_bundle_management_blocked",
	"role_bundle_apply_blocked",
}

MANAGER_ESCALATION_EVENTS = {
	"accounts_action_required",
	"stock_issue_failed",
	"dispensary_stock_issue_failed",
	"expired_stock_blocked",
	"dispensary_expired_stock_blocked",
	"insufficient_non_expired_stock",
	"dispensary_insufficient_non_expired_stock",
}

DOCUMENT_CONNECTED_USER_FIELDS = (
	"created_by",
	"document_owner",
	"owner",
	"requested_by",
	"requested_user",
	"requester",
	"assigned_to",
	"assigned_user",
	"handler",
	"handler_user",
	"front_desk_user",
	"responsible_user",
	"staff_user",
	"practitioner_user",
	"consulting_practitioner",
	"practitioner",
	"administered_by",
	"groomer",
	"applied_by",
	"user",
)

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
	"consultation_invoice_created": "notify_on_invoice_created",
	"payment_received": "notify_on_payment_received",
	"payment_pending": "notify_on_payment_received",
	"payment_reminder": "notify_on_payment_received",
	"accounts_action_required": "notify_on_accounts_action_required",
	"consultation_awaiting_payment": "notify_on_accounts_action_required",
	"consultation_sent_to_dispensary": "notify_on_accounts_action_required",
	"dispensary_confirmation_completed": "notify_on_payment_received",
	"dispensary_stock_issue_failed": "notify_on_accounts_action_required",
	"dispensary_expired_stock_blocked": "notify_on_accounts_action_required",
	"dispensary_insufficient_non_expired_stock": "notify_on_accounts_action_required",
	"stock_issue_failed": "notify_on_accounts_action_required",
	"expired_stock_blocked": "notify_on_accounts_action_required",
	"insufficient_non_expired_stock": "notify_on_accounts_action_required",
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
		event_key=event,
		reference_doctype="Veterinary Appointment",
		reference_name=appointment.name,
		context={
			"patient": appointment.patient,
			"primary_owner": appointment.primary_owner,
			"branch": appointment.branch,
			"practitioner": appointment.practitioner,
			"appointment_datetime": appointment.appointment_datetime,
			"status": appointment.status,
		},
	)


def create_notification_item(
	event_key: str,
	recipient_user: str,
	notification_title: str,
	message: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	action_url: str | None = None,
	priority: str = "Normal",
	payload: dict | None = None,
	idempotency_key: str | None = None,
) -> dict:
	"""Create one in-app notification item without invoking delivery channels."""
	if not frappe.db.exists("DocType", NOTIFICATION_ITEM_DOCTYPE):
		frappe.throw("Veterinary Notification Item is not installed.", frappe.ValidationError)

	idempotency_key = idempotency_key or build_notification_item_idempotency_key(
		event_key=event_key,
		recipient_user=recipient_user,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
		notification_title=notification_title,
		message=message,
	)
	existing_name = frappe.db.get_value(
		NOTIFICATION_ITEM_DOCTYPE,
		{"idempotency_key": idempotency_key},
		"name",
	)
	if existing_name:
		ensure_frappe_notification_log(existing_name)
		return {
			"created": False,
			"name": existing_name,
			"idempotency_key": idempotency_key,
		}

	doc = frappe.get_doc(
		{
			"doctype": NOTIFICATION_ITEM_DOCTYPE,
			"event_key": event_key,
			"recipient_user": recipient_user,
			"notification_title": notification_title,
			"message": message,
			"status": "Unread",
			"priority": priority or "Normal",
			"created_on": now_datetime(),
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"action_url": action_url,
			"idempotency_key": idempotency_key,
			"payload_json": json.dumps(payload or {}, sort_keys=True, default=str) if payload else None,
		}
	)
	doc.insert(ignore_permissions=True)
	ensure_frappe_notification_log(doc.name, notification_item=doc)
	return {
		"created": True,
		"name": doc.name,
		"idempotency_key": idempotency_key,
	}


def ensure_frappe_notification_log(notification_item_name: str, notification_item=None) -> str | None:
	if not frappe.db.exists("DocType", "Notification Log"):
		return None
	try:
		item = notification_item or frappe.get_doc(NOTIFICATION_ITEM_DOCTYPE, notification_item_name)
		if item.get("frappe_notification_log"):
			return item.get("frappe_notification_log")

		document_type = item.get("reference_doctype") or NOTIFICATION_ITEM_DOCTYPE
		document_name = item.get("reference_name") or item.name
		link = item.get("action_url") or _build_notification_log_link(document_type, document_name)
		existing_log = _find_existing_frappe_notification_log(item, document_type, document_name, link)
		if existing_log:
			frappe.db.set_value(
				NOTIFICATION_ITEM_DOCTYPE,
				item.name,
				"frappe_notification_log",
				existing_log,
				update_modified=False,
			)
			item.frappe_notification_log = existing_log
			return existing_log

		log = frappe.get_doc(
			{
				"doctype": "Notification Log",
				"subject": item.get("notification_title"),
				"for_user": item.get("recipient_user"),
				"type": "Alert",
				"email_content": item.get("message"),
				"document_type": document_type,
				"document_name": document_name,
				"from_user": "Administrator",
				"link": link,
				"read": 0,
			}
		)
		log.insert(ignore_permissions=True)
		frappe.db.set_value(
			NOTIFICATION_ITEM_DOCTYPE,
			item.name,
			"frappe_notification_log",
			log.name,
			update_modified=False,
		)
		item.frappe_notification_log = log.name
		return log.name
	except Exception:
		if getattr(frappe, "log_error", None):
			frappe.log_error(
				title="Veterinary Notification Log Mirror Failed",
				message=frappe.get_traceback() if getattr(frappe, "get_traceback", None) else "Notification Log mirror failed.",
			)
		return None


def _find_existing_frappe_notification_log(item, document_type: str | None, document_name: str | None, link: str | None) -> str | None:
	if not getattr(frappe.db, "get_value", None):
		return None
	filters = {
		"for_user": item.get("recipient_user"),
		"subject": item.get("notification_title"),
		"type": "Alert",
		"document_type": document_type,
		"document_name": document_name,
	}
	if link:
		filters["link"] = link
	try:
		return frappe.db.get_value("Notification Log", filters, "name")
	except Exception:
		return None


def _build_notification_log_link(document_type: str | None, document_name: str | None) -> str | None:
	if not document_type or not document_name:
		return None
	return "/app/{0}/{1}".format(
		frappe.scrub(document_type).replace("_", "-"),
		document_name,
	)


def build_notification_item_idempotency_key(
	event_key: str,
	recipient_user: str,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	notification_title: str | None = None,
	message: str | None = None,
) -> str:
	parts = [
		cstr(event_key),
		cstr(recipient_user),
		cstr(reference_doctype),
		cstr(reference_name),
		cstr(notification_title),
		cstr(message),
	]
	return sha256("\n".join(parts).encode("utf-8")).hexdigest()


def get_notification_request_user(requested_user: str | None = None) -> str | None:
	session_user = getattr(getattr(frappe, "session", None), "user", None)
	if requested_user and not session_user:
		return requested_user
	if not requested_user or requested_user == session_user:
		return session_user

	from vetedge.services.permissions import is_notification_admin

	if is_notification_admin(session_user):
		return requested_user
	frappe.throw("Not permitted to access another user's notifications.", frappe.PermissionError)
	return None


@frappe.whitelist()
def get_unread_notification_count(user: str | None = None) -> int:
	user = get_notification_request_user(user)
	if not user or user == "Guest":
		return 0
	return frappe.db.count(
		NOTIFICATION_ITEM_DOCTYPE,
		{
			"recipient_user": user,
			"status": "Unread",
		},
	)


@frappe.whitelist()
def mark_notification_read(notification_item: str, user: str | None = None) -> dict:
	return set_notification_item_status(notification_item, "Read", user=user)


@frappe.whitelist()
def mark_notification_unread(notification_item: str, user: str | None = None) -> dict:
	return set_notification_item_status(notification_item, "Unread", user=user)


@frappe.whitelist()
def acknowledge_notification(notification_item: str | None = None, notification_name: str | None = None, user: str | None = None) -> dict:
	notification_item = notification_item or notification_name
	if not notification_item:
		frappe.throw("Notification is required.", frappe.ValidationError)
	return set_notification_item_status(notification_item, "Acknowledged", user=user)


@frappe.whitelist()
def mark_notification_done(notification_item: str | None = None, notification_name: str | None = None, user: str | None = None) -> dict:
	notification_item = notification_item or notification_name
	if not notification_item:
		frappe.throw("Notification is required.", frappe.ValidationError)
	return set_notification_item_status(notification_item, "Done", user=user)


@frappe.whitelist()
def dismiss_notification(notification_item: str | None = None, notification_name: str | None = None, user: str | None = None) -> dict:
	notification_item = notification_item or notification_name
	if not notification_item:
		frappe.throw("Notification is required.", frappe.ValidationError)
	return set_notification_item_status(notification_item, "Dismissed", user=user)


@frappe.whitelist()
def archive_notification(notification_item: str | None = None, notification_name: str | None = None, user: str | None = None) -> dict:
	notification_item = notification_item or notification_name
	if not notification_item:
		frappe.throw("Notification is required.", frappe.ValidationError)
	return set_notification_item_status(notification_item, "Archived", user=user)


@frappe.whitelist()
def mark_all_notifications_read(user: str | None = None) -> dict:
	user = get_notification_request_user(user)
	if not user or user == "Guest":
		frappe.throw("User is required.", frappe.PermissionError)

	names = frappe.get_all(
		NOTIFICATION_ITEM_DOCTYPE,
		filters={"recipient_user": user, "status": "Unread"},
		pluck="name",
	)
	for name in names:
		frappe.db.set_value(
			NOTIFICATION_ITEM_DOCTYPE,
			name,
			{
				"status": "Read",
				"read_on": now_datetime(),
			},
			update_modified=True,
		)
	return {"updated": len(names)}


@frappe.whitelist()
def get_notification_feed(
	user: str | None = None,
	status: str | None = None,
	include_archived: bool = False,
	limit: int = 50,
) -> list[dict]:
	user = get_notification_request_user(user)
	if not user or user == "Guest":
		return []
	if status and status not in NOTIFICATION_ITEM_STATUSES:
		frappe.throw(f"Unsupported notification status: {status}", frappe.ValidationError)

	filters = {"recipient_user": user}
	if status:
		filters["status"] = status
	elif not include_archived:
		filters["status"] = ["!=", "Archived"]

	try:
		limit = max(1, min(int(limit or 50), 200))
	except Exception:
		limit = 50

	return frappe.get_all(
		NOTIFICATION_ITEM_DOCTYPE,
		filters=filters,
		fields=[
			"name",
			"notification_title",
			"message",
			"status",
			"priority",
			"event_key",
			"created_on",
			"read_on",
			"acknowledged_on",
			"completed_on",
			"dismissed_on",
			"archived_on",
			"reference_doctype",
			"reference_name",
			"action_url",
		],
		order_by="created_on desc",
		limit_page_length=limit,
	)


def set_notification_item_status(notification_item: str, status: str, user: str | None = None) -> dict:
	if status not in NOTIFICATION_ITEM_STATUSES:
		frappe.throw(f"Unsupported notification status: {status}", frappe.ValidationError)

	user = get_notification_request_user(user)
	if not can_update_notification_item(notification_item, user=user):
		frappe.throw("Not permitted to update this notification.", frappe.PermissionError)

	values = {"status": status}
	if status == "Unread":
		for timestamp_field in NOTIFICATION_ITEM_STATUS_TIMESTAMPS.values():
			values[timestamp_field] = None
	else:
		timestamp_field = NOTIFICATION_ITEM_STATUS_TIMESTAMPS.get(status)
		if timestamp_field:
			values[timestamp_field] = now_datetime()

	frappe.db.set_value(NOTIFICATION_ITEM_DOCTYPE, notification_item, values, update_modified=True)
	return {"name": notification_item, "status": status}


def can_update_notification_item(notification_item: str, user: str | None = None) -> bool:
	from vetedge.services.permissions import is_notification_admin

	user = user or getattr(getattr(frappe, "session", None), "user", None)
	if not user or user == "Guest":
		return False
	if is_notification_admin(user):
		return True
	recipient_user = frappe.db.get_value(NOTIFICATION_ITEM_DOCTYPE, notification_item, "recipient_user")
	return recipient_user == user


def emit_notification_event(
	event_key: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	payload: dict | None = None,
	context: dict | None = None,
	recipients: list | None = None,
	event: str | None = None,
) -> dict:
	event_key = event_key or event
	if not event_key:
		frappe.throw("Notification event key is required.", frappe.ValidationError)

	event_definition = get_notification_event_definition(event_key)
	if not event_definition:
		frappe.throw(f"Unsupported notification event: {event_key}", frappe.ValidationError)

	settings = get_notification_settings()
	merged_context = build_notification_context(
		event_key=event_key,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
		context=context or payload or {},
	)
	base_channels = [
		channel for channel in event_definition.default_channels if channel in settings.get("channels", [])
	]
	if not base_channels:
		base_channels = list(event_definition.default_channels)

	if not settings["enabled"]:
		log_skipped_event(event_key, base_channels, merged_context, reference_doctype, reference_name, settings, "notifications_disabled")
		return {"queued": False, "reason": "notifications_disabled"}

	if not is_event_enabled(event_key, settings):
		log_skipped_event(event_key, base_channels, merged_context, reference_doctype, reference_name, settings, "event_disabled")
		return {"queued": False, "reason": "event_disabled"}

	global_enabled_channels = [channel for channel in event_definition.default_channels if channel in settings.get("channels", [])]
	if not global_enabled_channels:
		log_skipped_event(
			event_key,
			list(event_definition.default_channels),
			merged_context,
			reference_doctype,
			reference_name,
			settings,
			"no_channels_configured",
		)
		return {"queued": False, "reason": "no_channels_configured"}

	resolved_recipients = resolve_notification_recipients(
		event_key=event_key,
		context=merged_context,
		explicit_recipients=recipients,
	)
	# Generate persistent in-app notifications for Clinical, Lab, and Pharmacy events
	from vetedge.services.clinical_lab_pharmacy_notifications import (
		handle_clinical_lab_pharmacy_notifications,
		SUPPORTED_EVENTS,
	)
	if event_key in SUPPORTED_EVENTS:
		try:
			handle_clinical_lab_pharmacy_notifications(
				event_key=event_key,
				reference_doctype=reference_doctype,
				reference_name=reference_name,
				recipients=resolved_recipients,
				context=merged_context,
			)
		except Exception:
			if getattr(frappe, "log_error", None):
				frappe.log_error("Failed to generate clinical/lab/pharmacy in-app notifications")

	if not resolved_recipients:
		log_skipped_event(
			event_key,
			global_enabled_channels,
			merged_context,
			reference_doctype,
			reference_name,
			settings,
			"no_recipients",
		)
		return {"queued": False, "reason": "no_recipients"}

	delivery = dispatch_notification_event(
		event_payload={
			"event_key": event_key,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"context": merged_context,
			"recipients": resolved_recipients,
		},
		settings=settings,
	)
	frappe.logger("vetedge.notifications").info(
		{
			"event_key": event_key,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"delivery": delivery,
		}
	)
	return {
		"queued": any(attempt["status"] in {"Queued", "Sent"} for attempt in delivery.get("attempts", [])),
		"event_key": event_key,
		"channels": global_enabled_channels,
		"delivery": delivery,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
	}


def dispatch_notification_event(event_payload: dict, settings: dict | None = None) -> dict:
	settings = settings or get_notification_settings()
	event_key = event_payload["event_key"]
	event_definition = get_notification_event_definition(event_key)
	context = event_payload.get("context") or {}
	backend = get_notification_backend(settings.get("notification_backend_mode", "local"))
	attempts = []

	for recipient in event_payload.get("recipients") or []:
		channels = resolve_recipient_channels(recipient, event_key, event_definition, settings)
		if not channels:
			attempt = {
				"channel": "Email",
				"recipient": recipient.get("address") or recipient.get("identifier"),
				"audience_type": recipient.get("audience_type"),
				"status": "Skipped",
				"backend_mode": settings.get("notification_backend_mode", "local"),
				"provider_reference": None,
				"error_message": "All channels are disabled by preference or global settings.",
			}
			log_notification_attempt(
				event_key=event_key,
				reference_doctype=event_payload.get("reference_doctype"),
				reference_name=event_payload.get("reference_name"),
				context=context,
				attempt=attempt,
			)
			attempts.append(attempt)
			continue

		results = backend.dispatch(
			event_definition=event_definition,
			recipient=recipient,
			channels=channels,
			context=context,
			settings=settings,
			reference_doctype=event_payload.get("reference_doctype"),
			reference_name=event_payload.get("reference_name"),
		)
		for attempt in results:
			log_notification_attempt(
				event_key=event_key,
				reference_doctype=event_payload.get("reference_doctype"),
				reference_name=event_payload.get("reference_name"),
				context=context,
				attempt=attempt,
			)
		attempts.extend(results)

	return {
		"backend_mode": settings.get("notification_backend_mode", "local"),
		"attempts": attempts,
	}


def resolve_notification_recipients(
	event_key: str,
	context: dict,
	explicit_recipients: list | None = None,
) -> list[dict]:
	if explicit_recipients:
		return filter_notification_recipients(normalize_explicit_recipients(explicit_recipients))

	recipients: list[dict] = []
	if event_key in OWNER_EVENTS:
		recipients.extend(get_owner_recipients(context))

	recipients.extend(get_internal_recipients(event_key, context))
	return filter_notification_recipients(deduplicate_recipients(recipients))


def normalize_explicit_recipients(explicit_recipients: list) -> list[dict]:
	recipients = []
	for recipient in explicit_recipients:
		if isinstance(recipient, dict):
			recipients.append(
				{
					"identifier": recipient.get("identifier") or recipient.get("recipient") or recipient.get("user") or recipient.get("customer") or recipient.get("email"),
					"address": recipient.get("address") or recipient.get("email"),
					"audience_type": recipient.get("audience_type") or "Explicit",
					"preference_key": recipient.get("preference_key") or recipient.get("user") or recipient.get("customer") or recipient.get("email"),
				}
			)
		else:
			recipients.append(
				{
					"identifier": cstr(recipient),
					"address": cstr(recipient) if "@" in cstr(recipient) else None,
					"audience_type": "Explicit",
					"preference_key": cstr(recipient),
				}
			)
	return deduplicate_recipients(recipients)


def get_owner_recipients(context: dict) -> list[dict]:
	recipients = []
	customer = context.get("customer") or context.get("primary_owner")
	for email in get_owner_email_recipients(context):
		recipients.append(
			{
				"identifier": customer or email,
				"address": email,
				"audience_type": "Owner",
				"preference_key": customer or email,
				"customer": customer,
			}
		)
	return recipients


def get_internal_recipients(event_key: str, context: dict) -> list[dict]:
	branch = context.get("service_branch") or context.get("branch")
	if event_key in ADMIN_ESCALATION_EVENTS:
		return resolve_admin_escalation_recipients(branch=branch)
	if event_key in MANAGER_ESCALATION_EVENTS:
		return resolve_manager_escalation_recipients(branch=branch)
	return get_document_connected_recipients(context)


def resolve_admin_escalation_recipients(branch: str | None = None) -> list[dict]:
	"""Role broadcast is reserved for explicit admin/security escalation events."""
	return get_role_recipients(
		{"System Manager", "VetEdge Administrator", "Branch Manager", "VetEdge Branch Manager"},
		branch=branch,
		audience_type="Admin Escalation",
	)


def resolve_manager_escalation_recipients(branch: str | None = None) -> list[dict]:
	return get_role_recipients(
		{"VetEdge Administrator", "Branch Manager", "VetEdge Branch Manager", "Accounts Manager"},
		branch=branch,
		audience_type="Manager Escalation",
	)


def get_document_connected_recipients(context: dict) -> list[dict]:
	recipients = []
	for fieldname in DOCUMENT_CONNECTED_USER_FIELDS:
		for user in _split_user_values(context.get(fieldname)):
			recipient = get_user_recipient(user, audience_type=_audience_type_for_user_field(fieldname))
			if recipient:
				recipients.append(recipient)
	return recipients


def _split_user_values(value) -> list[str]:
	if value in (None, ""):
		return []
	if isinstance(value, (list, tuple, set)):
		values = value
	else:
		values = [value]
	users = []
	for raw_value in values:
		for user in cstr(raw_value).replace("\n", ",").split(","):
			user = user.strip()
			if user:
				users.append(user)
	return users


def _audience_type_for_user_field(fieldname: str) -> str:
	if fieldname in {"created_by", "document_owner", "owner"}:
		return "Creator"
	if fieldname in {"practitioner_user", "consulting_practitioner", "practitioner", "administered_by"}:
		return "Practitioner"
	if fieldname == "groomer":
		return "Grooming"
	if fieldname in {"front_desk_user", "handler", "handler_user", "responsible_user", "assigned_to", "assigned_user"}:
		return "Assigned Staff"
	return "Internal Staff"


def get_user_recipient(user: str | None, audience_type: str = "Internal Staff", allow_system: bool = False) -> dict | None:
	user = cstr(user).strip()
	if not user:
		return None
	if not allow_system and user in SYSTEM_NOTIFICATION_USERS:
		return None
	if not is_notification_user_enabled(user):
		return None
	email = get_user_email(user)
	if not email:
		return None
	return {
		"identifier": user,
		"address": email,
		"audience_type": audience_type,
		"preference_key": user,
		"user": user,
	}


def is_notification_user_enabled(user: str | None) -> bool:
	user = cstr(user).strip()
	if not user:
		return False
	if user == "Guest":
		return False
	try:
		if not frappe.db.exists("User", user):
			return "@" in user and user != "Administrator"
	except Exception:
		pass
	try:
		enabled = frappe.db.get_value("User", user, "enabled")
		return bool(enabled)
	except Exception:
		return user != "Administrator"


def get_practitioner_recipients(context: dict) -> list[dict]:
	practitioner = context.get("practitioner") or context.get("consulting_practitioner") or context.get("requested_by") or context.get("administered_by") or context.get("groomer")
	if not practitioner and context.get("consultation"):
		practitioner = frappe.db.get_value("Veterinary Consultation", context["consultation"], "consulting_practitioner")
	if not practitioner:
		return []
	recipient = get_user_recipient(practitioner, audience_type="Practitioner")
	if not recipient:
		return []
	return [recipient]


def get_groomer_recipients(context: dict) -> list[dict]:
	groomer = context.get("groomer")
	if not groomer:
		return []
	recipient = get_user_recipient(groomer, audience_type="Grooming")
	if not recipient:
		return []
	return [recipient]


def get_role_recipients(roles: set[str], branch: str | None = None, audience_type: str = "Internal Staff") -> list[dict]:
	users = frappe.get_all(
		"Has Role",
		filters={"role": ["in", list(roles)], "parenttype": "User"},
		pluck="parent",
	)
	if not users:
		return []

	users = [
		user
		for user in users
		if is_notification_user_enabled(user)
	]
	if branch and frappe.db.exists("DocType", "Branch User Assignment"):
		branch_users = [
			user for user in users if branch in get_assigned_branches(user)
		]
		if branch_users:
			users = branch_users

	recipients = []
	for user in users:
		recipient = get_user_recipient(user, audience_type=audience_type, allow_system=True)
		if recipient:
			recipients.append(recipient)
	return recipients


def deduplicate_recipients(recipients: list[dict]) -> list[dict]:
	deduped = []
	seen = set()
	for recipient in recipients:
		key = cstr(recipient.get("address") or recipient.get("preference_key") or recipient.get("user") or recipient.get("identifier")).lower()
		if key in seen:
			continue
		seen.add(key)
		deduped.append(recipient)
	return deduped


def filter_notification_recipients(recipients: list[dict]) -> list[dict]:
	filtered = []
	for recipient in recipients:
		user = recipient.get("user")
		identifier = recipient.get("identifier")
		if not user and identifier in SYSTEM_NOTIFICATION_USERS:
			continue
		if user and not is_notification_user_enabled(user):
			continue
		if not user and identifier and "@" in cstr(identifier):
			try:
				if frappe.db.exists("User", identifier) and not is_notification_user_enabled(identifier):
					continue
			except Exception:
				pass
		filtered.append(recipient)
	return filtered


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
		for user in frappe.get_all(
			"Portal User",
			filters={"parenttype": "Customer", "parent": customer},
			pluck="user",
		):
			if is_notification_user_enabled(user):
				recipients.add(user)

	return recipients


def get_user_email(user: str | None) -> str | None:
	if not user:
		return None
	return frappe.db.get_value("User", user, "email") or frappe.db.get_value("User", user, "name")


def resolve_recipient_channels(
	recipient: dict,
	event_key: str,
	event_definition,
	settings: dict,
) -> list[str]:
	global_channels = [channel for channel in event_definition.default_channels if channel in settings.get("channels", [])]
	preference = get_notification_preference(recipient, event_key)
	if not preference:
		return global_channels

	channels = []
	if preference.get("email_enabled") and "Email" in global_channels:
		channels.append("Email")
	if preference.get("sms_enabled") and "SMS" in global_channels:
		channels.append("SMS")
	if preference.get("whatsapp_enabled") and "WhatsApp" in global_channels:
		channels.append("WhatsApp")
	return channels


def get_notification_preference(recipient: dict, event_key: str) -> dict | None:
	if not frappe.db.exists("DocType", "VetEdge Notification Preference"):
		return None
	preference_key = recipient.get("preference_key") or recipient.get("identifier") or recipient.get("address")
	if not preference_key:
		return None
	rows = frappe.get_all(
		"VetEdge Notification Preference",
		filters={"recipient": preference_key, "event_key": event_key, "is_active": 1},
		fields=["email_enabled", "sms_enabled", "whatsapp_enabled"],
		limit=1,
	)
	return rows[0] if rows else None


def build_notification_context(
	event_key: str,
	reference_doctype: str | None,
	reference_name: str | None,
	context: dict,
) -> dict:
	context = dict(context or {})
	context = enrich_notification_context(context, reference_doctype, reference_name)
	context.setdefault("event_key", event_key)
	context.setdefault("reference_doctype", reference_doctype)
	context.setdefault("reference_name", reference_name)
	context.setdefault("clinic_name", get_clinic_brand_name())
	context.setdefault("clinic_tagline", "")
	context.setdefault("email_template", get_notification_email_template(event_key))
	return sanitize_notification_context(context)


def enrich_notification_context(
	context: dict,
	reference_doctype: str | None,
	reference_name: str | None,
) -> dict:
	context = dict(context or {})
	context = hydrate_reference_context(context, reference_doctype, reference_name)
	context = apply_notification_aliases(context, reference_doctype, reference_name)
	return context


def hydrate_reference_context(
	context: dict,
	reference_doctype: str | None,
	reference_name: str | None,
) -> dict:
	if not reference_doctype or not reference_name:
		return context
	if not frappe.db.exists(reference_doctype, reference_name):
		return context
	if context.get("document_owner") in (None, ""):
		try:
			document_owner = frappe.db.get_value(reference_doctype, reference_name, "owner")
			if document_owner:
				context["document_owner"] = document_owner
				context.setdefault("created_by", document_owner)
		except Exception:
			pass

	field_map = {
		"Sales Invoice": (
			"customer",
			"grand_total",
			"outstanding_amount",
			"remarks",
		),
		"Veterinary Appointment": (
			"patient",
			"primary_owner",
			"branch",
			"practitioner",
			"appointment_datetime",
			"status",
		),
		"Veterinary Consultation": (
			"patient",
			"primary_owner",
			"service_branch",
			"consulting_practitioner",
			"status",
			"linked_invoice",
		),
		"Veterinary Lab Order": (
			"patient",
			"primary_owner",
			"consultation",
			"service_branch",
			"requested_by",
			"status",
		),
		"Veterinary Vaccination Record": (
			"patient",
			"primary_owner",
			"service_branch",
			"vaccine",
			"administered_by",
			"vaccination_date",
			"next_due_date",
			"linked_invoice",
			"linked_consultation",
		),
		"Pet Grooming Appointment": (
			"patient",
			"primary_owner",
			"service_branch",
			"grooming_service",
			"groomer",
			"scheduled_datetime",
			"status",
			"linked_invoice",
		),
		"Pet Grooming Session": (
			"patient",
			"primary_owner",
			"service_branch",
			"grooming_service",
			"groomer",
			"start_time",
			"end_time",
			"status",
			"linked_invoice",
		),
		"Pet Boarding Booking": (
			"patient",
			"primary_owner",
			"service_branch",
			"kennel",
			"check_in_date",
			"expected_check_out_date",
			"actual_check_out_date",
			"linked_invoice",
			"billable_days",
			"total_boarding_charge",
		),
		"Pet Boarding Stay": (
			"patient",
			"primary_owner",
			"service_branch",
			"kennel",
			"booking",
			"status",
		),
	}

	fields = field_map.get(reference_doctype)
	if not fields:
		return context

	values = frappe.db.get_value(reference_doctype, reference_name, list(fields), as_dict=True) or {}
	for fieldname in fields:
		if context.get(fieldname) in (None, "") and values.get(fieldname) not in (None, ""):
			context[fieldname] = values.get(fieldname)

	return context


def apply_notification_aliases(
	context: dict,
	reference_doctype: str | None,
	reference_name: str | None,
) -> dict:
	context = dict(context or {})
	context.setdefault("record", reference_name or context.get("reference_name"))
	context.setdefault("service_branch", context.get("branch"))
	context.setdefault("branch", context.get("service_branch"))

	if context.get("patient") and not context.get("patient_name"):
		patient_data = frappe.db.get_value(
			"Veterinary Patient",
			context["patient"],
			["patient_name", "primary_owner", "default_branch"],
			as_dict=True,
		) or {}
		context.setdefault("patient_name", patient_data.get("patient_name"))
		context.setdefault("primary_owner", patient_data.get("primary_owner"))
		context.setdefault("service_branch", patient_data.get("default_branch"))
		context.setdefault("branch", patient_data.get("default_branch"))

	customer = context.get("customer") or context.get("primary_owner")
	if customer:
		context.setdefault("customer", customer)
		if not context.get("owner_name"):
			context["owner_name"] = get_customer_display_name(customer)

	practitioner_user = (
		context.get("consulting_practitioner")
		or context.get("practitioner")
		or context.get("requested_by")
		or context.get("administered_by")
		or context.get("groomer")
	)
	if practitioner_user:
		context.setdefault("practitioner_user", practitioner_user)
		context["practitioner"] = get_user_display_name(practitioner_user)

	staff_user = (
		context.get("requested_by")
		or context.get("administered_by")
		or context.get("groomer")
		or context.get("applied_by")
		or context.get("user")
		or practitioner_user
	)
	if staff_user and not context.get("staff_name"):
		context["staff_name"] = get_user_display_name(staff_user)

	if context.get("applied_by"):
		context["applied_by"] = get_user_display_name(context["applied_by"])
	if context.get("user") and "@" in cstr(context.get("user")):
		context["user"] = get_user_display_name(context["user"])

	if reference_doctype == "Veterinary Lab Order":
		context.setdefault("lab_order", reference_name)
	if reference_doctype == "Veterinary Consultation":
		context.setdefault("consultation", reference_name)
	if reference_doctype == "Sales Invoice":
		context.setdefault("invoice", reference_name)

	context.setdefault("consultation", context.get("linked_consultation"))
	context.setdefault("invoice", context.get("linked_invoice"))

	if not context.get("amount"):
		for candidate in (
			context.get("outstanding_amount"),
			context.get("paid_amount"),
			context.get("grand_total"),
			context.get("total_boarding_charge"),
		):
			if candidate not in (None, ""):
				context["amount"] = candidate
				break

	if context.get("vaccination_date") and not context.get("administered_on"):
		context["administered_on"] = context.get("vaccination_date")

	if context.get("scheduled_datetime") and not context.get("appointment_datetime"):
		context["appointment_datetime"] = context.get("scheduled_datetime")

	return context


def sanitize_notification_context(context: dict) -> dict:
	sanitized = {}
	for key, value in (context or {}).items():
		if any(marker in cstr(key).lower() for marker in ("note", "notes", "diagnosis", "symptom", "medical")):
			continue
		sanitized[key] = value
	return sanitized


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


def get_customer_display_name(customer: str | None) -> str | None:
	if not customer:
		return None
	if not frappe.db.exists("Customer", customer):
		return customer
	return (
		frappe.db.get_value("Customer", customer, "customer_name")
		or frappe.db.get_value("Customer", customer, "name")
	)


def get_user_display_name(user: str | None) -> str | None:
	if not user:
		return None
	if not frappe.db.exists("User", user):
		return user
	return (
		frappe.db.get_value("User", user, "full_name")
		or frappe.db.get_value("User", user, "first_name")
		or frappe.db.get_value("User", user, "name")
	)


def log_notification_attempt(
	event_key: str,
	reference_doctype: str | None,
	reference_name: str | None,
	context: dict,
	attempt: dict,
) -> None:
	try:
		if not frappe.db.exists("DocType", "VetEdge Notification Log"):
			return
		event_definition = get_notification_event_definition(event_key)
		doc = frappe.get_doc(
			{
				"doctype": "VetEdge Notification Log",
				"event_key": event_key,
				"channel": attempt.get("channel") or "Email",
				"recipient": attempt.get("recipient"),
				"audience_type": attempt.get("audience_type") or (event_definition.audience if event_definition else None),
				"reference_doctype": reference_doctype,
				"reference_name": reference_name,
				"status": attempt.get("status") or "Skipped",
				"backend_mode": attempt.get("backend_mode") or "local",
				"provider_reference": attempt.get("provider_reference"),
				"error_message": attempt.get("error_message"),
				"created_on": now_datetime(),
				"sent_on": now_datetime() if attempt.get("status") == "Sent" else None,
				"payload_preview": build_payload_preview(context),
			}
		)
		doc.insert(ignore_permissions=True)
	except Exception:
		pass


def build_payload_preview(payload: dict) -> str:
	if not payload:
		return ""
	return json.dumps(sanitize_notification_context(payload), default=str, ensure_ascii=True)[:1400]


def log_skipped_event(
	event_key: str,
	channels: list[str],
	context: dict,
	reference_doctype: str | None,
	reference_name: str | None,
	settings: dict,
	reason: str,
) -> None:
	for channel in channels or ["Email"]:
		log_notification_attempt(
			event_key=event_key,
			reference_doctype=reference_doctype,
			reference_name=reference_name,
			context=context,
			attempt={
				"channel": channel,
				"recipient": None,
				"audience_type": None,
				"status": "Skipped",
				"backend_mode": settings.get("notification_backend_mode", "local"),
				"provider_reference": None,
				"error_message": reason,
			},
		)


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
		now_datetime(),
		hours=int(settings.get("appointment_reminder_hours") or settings.get("appointment_reminder_hours_before") or 24),
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
		try:
			result = notify_appointment_event(appointment, "appointment_reminder")
		except Exception as exc:
			_notify_appointment_reminder_failed_safely(appointment, reason=cstr(exc))
			results.append({"queued": False, "reason": "appointment_reminder_failed", "appointment": appointment.name})
			continue
		results.append(result)
		if result.get("queued"):
			frappe.db.set_value(
				"Veterinary Appointment",
				appointment.name,
				{"reminder_sent": 1, "reminder_sent_on": now_datetime()},
				update_modified=False,
			)
			_notify_appointment_reminder_sent_safely(appointment)
		else:
			_notify_appointment_reminder_failed_safely(appointment, reason=result.get("reason"))

	return results


def _notify_appointment_reminder_sent_safely(appointment) -> None:
	try:
		from vetedge.services.appointment_notifications import notify_appointment_reminder_sent

		notify_appointment_reminder_sent(appointment)
	except Exception:
		pass


def _notify_appointment_reminder_failed_safely(appointment, reason: str | None = None) -> None:
	try:
		from vetedge.services.appointment_notifications import notify_appointment_reminder_failed

		notify_appointment_reminder_failed(appointment, reason=reason)
	except Exception:
		pass


def send_due_vaccination_notifications() -> list[dict]:
	settings = get_notification_settings()
	if not settings["enabled"]:
		return []

	results = []

	# Daily: generate the persistent in-app notifications (Veterinary Notification Items)
	try:
		from vetedge.services.vaccination_notifications import run_vaccination_notification_checks
		res_dict = run_vaccination_notification_checks()
		for val in res_dict.values():
			if isinstance(val, list):
				results.extend(val)
	except Exception:
		if getattr(frappe, "log_error", None):
			frappe.log_error("Failed to run vaccination notification checks (new)")

	# Preserve the original active notifications behavior (emails/SMS)
	records = query_due_vaccination_notifications(
		due_soon_days=int(settings.get("vaccination_due_reminder_days") or 7)
	)
	for row in records:
		event_key = "vaccination_overdue" if row["due_state"] == "Overdue" else "vaccination_due_soon"
		if already_notified_recently(event_key, "Veterinary Vaccination Record", row["name"]):
			continue
		results.append(
			emit_notification_event(
				event_key=event_key,
				reference_doctype="Veterinary Vaccination Record",
				reference_name=row["name"],
				context=row,
			)
		)
	return results


def query_due_vaccination_notifications(due_soon_days: int = 7) -> list[dict]:
	today = getdate()
	rows = frappe.get_all(
		"Veterinary Vaccination Record",
		filters={"status": "Administered", "next_due_date": ["is", "set"]},
		fields=["name", "patient", "primary_owner", "vaccine", "service_branch", "next_due_date"],
		order_by="next_due_date asc",
	)
	results = []
	for row in rows:
		due_date = getdate(row.get("next_due_date"))
		if due_date < today:
			row["due_state"] = "Overdue"
		elif due_date <= add_days(today, due_soon_days):
			row["due_state"] = "Due Soon"
		else:
			continue
		row["days_until_due"] = (due_date - today).days
		results.append(row)
	return results


def send_payment_pending_reminders() -> list[dict]:
	settings = get_notification_settings()
	if not settings["enabled"]:
		return []

	payment_reminder_days = cint_or_default(settings.get("payment_reminder_days"), 3)
	invoices = frappe.get_all(
		"Sales Invoice",
		filters={"docstatus": 1, "outstanding_amount": [">", 0]},
		fields=_get_sales_invoice_notification_fields(),
		order_by="due_date asc",
	)
	results = []
	today = getdate()
	for row in invoices:
		due_date = getdate(row.get("due_date") or today)
		if due_date > add_days(today, payment_reminder_days):
			continue
		if already_notified_recently("payment_pending", "Sales Invoice", row["name"]):
			continue
		results.append(
			emit_notification_event(
				event_key="payment_pending",
				reference_doctype="Sales Invoice",
				reference_name=row["name"],
				context={
					"invoice": row["name"],
					"customer": row.get("customer"),
					"outstanding_amount": row.get("outstanding_amount"),
					"due_date": row.get("due_date"),
					"branch": row.get("branch"),
				},
			)
		)
	return results


def already_notified_recently(
	event_key: str,
	reference_doctype: str,
	reference_name: str,
	preference_key: str | None = None,
) -> bool:
	if not frappe.db.exists("DocType", "VetEdge Notification Log"):
		return False
	filters = {
		"event_key": event_key,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"status": ["in", ["Queued", "Sent"]],
		"created_on": [">=", f"{nowdate()} 00:00:00"],
	}
	if preference_key:
		filters["recipient"] = preference_key
	return bool(frappe.db.count("VetEdge Notification Log", filters=filters))


def cint_or_default(value, default: int) -> int:
	try:
		return int(value)
	except Exception:
		return default


def _get_sales_invoice_notification_fields() -> list[str]:
	fields = ["name", "customer", "outstanding_amount", "due_date"]
	if frappe.get_meta("Sales Invoice").has_field("branch"):
		fields.append("branch")
	return fields
