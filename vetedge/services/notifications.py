from __future__ import annotations

import json

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
		return normalize_explicit_recipients(explicit_recipients)

	recipients: list[dict] = []
	if event_key in OWNER_EVENTS:
		recipients.extend(get_owner_recipients(context))

	recipients.extend(get_internal_recipients(event_key, context))
	return deduplicate_recipients(recipients)


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
	if event_key == "lab_result_ready_for_review":
		recipients = get_practitioner_recipients(context)
		if recipients:
			return recipients
		return get_role_recipients(LAB_REVIEW_NOTIFICATION_ROLES, branch=branch, audience_type="Doctor")

	if event_key in {"lab_order_created", "lab_sample_collected", "lab_result_entered"}:
		return get_role_recipients(LAB_NOTIFICATION_ROLES, branch=branch, audience_type="Lab")

	if event_key in {
		"accounts_action_required",
		"consultation_awaiting_payment",
		"payment_received",
		"payment_pending",
		"consultation_invoice_created",
		"invoice_created",
		"boarding_invoice_created",
		"grooming_invoice_created",
	}:
		return get_role_recipients(ACCOUNTS_NOTIFICATION_ROLES, branch=branch, audience_type="Accounts")

	if event_key in {
		"dispensary_request_created",
		"consultation_sent_to_dispensary",
		"dispensary_confirmed",
		"dispensary_confirmation_completed",
		"dispensary_stock_issue_failed",
		"stock_issue_failed",
		"dispensary_expired_stock_blocked",
		"expired_stock_blocked",
		"dispensary_insufficient_non_expired_stock",
		"insufficient_non_expired_stock",
	}:
		return get_role_recipients(DISPENSARY_NOTIFICATION_ROLES, branch=branch, audience_type="Dispensary")

	if event_key.startswith("boarding_"):
		return get_role_recipients(BOARDING_NOTIFICATION_ROLES, branch=branch, audience_type="Boarding")

	if event_key.startswith("grooming_"):
		recipients = get_groomer_recipients(context)
		if recipients:
			return recipients
		return get_role_recipients(GROOMING_NOTIFICATION_ROLES, branch=branch, audience_type="Grooming")

	if event_key in {
		"owner_appointment_request_received",
		"guest_appointment_request_received",
		"guest_appointment_ready_for_approval",
		"registration_request_received",
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
	}:
		return get_role_recipients(STAFF_NOTIFICATION_ROLES | {"System Manager", "VetEdge Administrator"}, branch=branch, audience_type="Internal Staff")

	if event_key == "consultation_ready_for_treatment":
		return get_practitioner_recipients(context) or get_role_recipients(STAFF_NOTIFICATION_ROLES, branch=branch, audience_type="Internal Staff")

	return get_role_recipients(STAFF_NOTIFICATION_ROLES, branch=branch, audience_type="Internal Staff")


def get_practitioner_recipients(context: dict) -> list[dict]:
	practitioner = context.get("practitioner") or context.get("consulting_practitioner") or context.get("requested_by") or context.get("administered_by") or context.get("groomer")
	if not practitioner and context.get("consultation"):
		practitioner = frappe.db.get_value("Veterinary Consultation", context["consultation"], "consulting_practitioner")
	if not practitioner:
		return []
	email = get_user_email(practitioner)
	if not email:
		return []
	return [
		{
			"identifier": practitioner,
			"address": email,
			"audience_type": "Practitioner",
			"preference_key": practitioner,
			"user": practitioner,
		}
	]


def get_groomer_recipients(context: dict) -> list[dict]:
	groomer = context.get("groomer")
	if not groomer:
		return []
	email = get_user_email(groomer)
	if not email:
		return []
	return [
		{
			"identifier": groomer,
			"address": email,
			"audience_type": "Grooming",
			"preference_key": groomer,
			"user": groomer,
		}
	]


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
		if frappe.db.get_value("User", user, "enabled")
	]
	if branch and frappe.db.exists("DocType", "Branch User Assignment"):
		branch_users = [
			user for user in users if branch in get_assigned_branches(user)
		]
		if branch_users:
			users = branch_users

	recipients = []
	for user in users:
		email = get_user_email(user)
		if not email:
			continue
		recipients.append(
			{
				"identifier": user,
				"address": email,
				"audience_type": audience_type,
				"preference_key": user,
				"user": user,
			}
		)
	return recipients


def deduplicate_recipients(recipients: list[dict]) -> list[dict]:
	deduped = []
	seen = set()
	for recipient in recipients:
		key = (
			recipient.get("preference_key") or recipient.get("identifier"),
			recipient.get("address"),
			recipient.get("audience_type"),
		)
		if key in seen:
			continue
		seen.add(key)
		deduped.append(recipient)
	return deduped


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


def send_due_vaccination_notifications() -> list[dict]:
	settings = get_notification_settings()
	if not settings["enabled"]:
		return []

	records = query_due_vaccination_notifications(
		due_soon_days=int(settings.get("vaccination_due_reminder_days") or 7)
	)
	results = []
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
