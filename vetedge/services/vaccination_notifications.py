from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, cstr, getdate, nowdate

from vetedge.services.notifications import (
	create_notification_item,
	get_role_recipients,
	get_user_recipient,
	get_notification_settings,
)

VACCINATION_RECORD_DOCTYPE = "Veterinary Vaccination Record"
HIGH_VISIBILITY_ROLES = {
	"VetEdge Front Desk",
	"Branch Manager",
	"VetEdge Branch Manager",
	"VetEdge Administrator",
}


def notify_vaccination_due(doc) -> list[dict]:
	return create_vaccination_notifications("vaccination_due", doc)


def notify_vaccination_overdue(doc) -> list[dict]:
	return create_vaccination_notifications("vaccination_overdue", doc)


def notify_vaccination_reminder_sent(doc) -> list[dict]:
	return create_vaccination_notifications("vaccination_reminder_sent", doc)


def notify_vaccination_reminder_failed(doc, reason: str | None = None) -> list[dict]:
	return create_vaccination_notifications("vaccination_reminder_failed", doc, failure_reason=reason)


def create_vaccination_notifications(event_key: str, doc, **kwargs) -> list[dict]:
	config_map = {
		"vaccination_due": {
			"title": "Veterinary Vaccination Due",
			"category": "Vaccination",
			"priority": "Normal",
		},
		"vaccination_overdue": {
			"title": "Veterinary Vaccination Overdue",
			"category": "Vaccination",
			"priority": "High",
		},
		"vaccination_reminder_sent": {
			"title": "Veterinary Vaccination Reminder Sent",
			"category": "Vaccination",
			"priority": "Normal",
		},
		"vaccination_reminder_failed": {
			"title": "Veterinary Vaccination Reminder Failed",
			"category": "Vaccination",
			"priority": "High",
		},
	}
	config = config_map.get(event_key)
	if not config:
		return []

	results = []
	try:
		recipients = resolve_vaccination_notification_recipients(doc)
		due_date = cstr(doc.get("next_due_date"))

		for recipient_user in recipients:
			idempotency_key = f"{event_key}::{doc.get('name')}::{due_date}::{recipient_user}"
			message = build_vaccination_notification_message(event_key, doc, **kwargs)
			
			results.append(
				create_notification_item(
					event_key=event_key,
					recipient_user=recipient_user,
					notification_title=config["title"],
					message=message,
					reference_doctype=VACCINATION_RECORD_DOCTYPE,
					reference_name=doc.get("name"),
					action_url=f"/app/veterinary-vaccination-record/{doc.get('name')}",
					priority=config["priority"],
					payload={
						"category": config["category"],
						"vaccination_record": doc.get("name"),
						"patient": doc.get("patient"),
						"primary_owner": doc.get("primary_owner"),
						"service_branch": doc.get("service_branch"),
						"vaccine": doc.get("vaccine"),
						"next_due_date": due_date,
						**kwargs,
					},
					idempotency_key=idempotency_key,
				)
			)
	except Exception:
		_log_vaccination_notification_error(event_key, doc)
	return results


def resolve_vaccination_notification_recipients(doc) -> list[str]:
	recipients = []
	
	# 1. Assigned practitioner (administered_by)
	if doc.get("administered_by"):
		recipient = get_user_recipient(doc.get("administered_by"), audience_type="Vaccination")
		if recipient and recipient.get("user"):
			recipients.append(recipient["user"])

	# 2. Document creator/owner
	if doc.get("owner"):
		recipient = get_user_recipient(doc.get("owner"), audience_type="Vaccination")
		if recipient and recipient.get("user"):
			recipients.append(recipient["user"])

	# 3. Branch reception/users and branch manager/admin
	branch = doc.get("service_branch")
	for recipient in get_role_recipients(HIGH_VISIBILITY_ROLES, branch=branch, audience_type="Vaccination Follow-up"):
		if recipient.get("user"):
			recipients.append(recipient["user"])

	# 4. Fallback if empty
	if not recipients:
		# Try branch doctors/nurses
		fallback_roles = {"VetEdge Doctor", "Veterinary Nurse"}
		for recipient in get_role_recipients(fallback_roles, branch=branch, audience_type="Vaccination Follow-up"):
			if recipient.get("user"):
				recipients.append(recipient["user"])
		
		# If still empty, try System Manager or Administrator
		if not recipients:
			for recipient in get_role_recipients({"System Manager"}, branch=branch, audience_type="Vaccination Follow-up"):
				if recipient.get("user"):
					recipients.append(recipient["user"])
			# Absolute fallback to Administrator
			if not recipients and frappe.db.exists("User", "Administrator"):
				admin_rec = get_user_recipient("Administrator", audience_type="Vaccination", allow_system=True)
				if admin_rec and admin_rec.get("user"):
					recipients.append(admin_rec["user"])

	return _dedupe_users(recipients)


def build_vaccination_notification_message(event_key: str, doc, **kwargs) -> str:
	doc_name = doc.get("name")
	vaccine = doc.get("vaccine")
	patient = doc.get("patient")
	due_date = doc.get("next_due_date")
	
	if event_key == "vaccination_due":
		return f"Veterinary vaccination record {doc_name} for vaccine {vaccine} is due today ({due_date}) for patient {patient}."
	if event_key == "vaccination_overdue":
		return f"Veterinary vaccination record {doc_name} for vaccine {vaccine} is overdue since {due_date} for patient {patient}."
	if event_key == "vaccination_reminder_sent":
		return f"Veterinary vaccination reminder was sent for {doc_name}."
	if event_key == "vaccination_reminder_failed":
		reason = cstr(kwargs.get("failure_reason")).strip()
		return f"Veterinary vaccination reminder failed for {doc_name}.{(' ' + reason) if reason else ''}"
	return f"Veterinary vaccination record {doc_name} notification."


def run_vaccination_notification_checks() -> dict:
	return {
		"vaccination_due": send_due_vaccination_notifications(),
		"vaccination_overdue": send_overdue_vaccination_notifications(),
	}


def send_due_vaccination_notifications(limit: int = 100) -> list[dict]:
	if not _vaccination_notifications_available():
		return []

	settings = get_notification_settings()
	if not settings or not settings.get("enabled"):
		return []

	due_soon_days = int(settings.get("vaccination_due_reminder_days") or 7)
	today = getdate()
	
	rows = frappe.get_all(
		VACCINATION_RECORD_DOCTYPE,
		filters={"status": "Administered", "next_due_date": ["is", "set"]},
		fields=["name", "patient", "primary_owner", "vaccine", "service_branch", "next_due_date", "administered_by", "owner"],
		order_by="next_due_date asc",
		limit_page_length=limit,
	)
	
	results = []
	for row in rows:
		patient_status = frappe.db.get_value("Veterinary Patient", row.get("patient"), "status")
		if patient_status in ("Inactive", "Deceased", "Archived"):
			continue
			
		due_date = getdate(row.get("next_due_date"))
		if due_date >= today and due_date <= add_days(today, due_soon_days):
			results.extend(notify_vaccination_due(row))
			
	return results


def send_overdue_vaccination_notifications(limit: int = 100) -> list[dict]:
	if not _vaccination_notifications_available():
		return []

	settings = get_notification_settings()
	if not settings or not settings.get("enabled"):
		return []

	today = getdate()
	
	rows = frappe.get_all(
		VACCINATION_RECORD_DOCTYPE,
		filters={"status": "Administered", "next_due_date": ["is", "set"]},
		fields=["name", "patient", "primary_owner", "vaccine", "service_branch", "next_due_date", "administered_by", "owner"],
		order_by="next_due_date asc",
		limit_page_length=limit,
	)
	
	results = []
	for row in rows:
		patient_status = frappe.db.get_value("Veterinary Patient", row.get("patient"), "status")
		if patient_status in ("Inactive", "Deceased", "Archived"):
			continue
			
		due_date = getdate(row.get("next_due_date"))
		if due_date < today:
			results.extend(notify_vaccination_overdue(row))
			
	return results


@frappe.whitelist()
def diagnose_vaccination_notifications(
	vaccination_record_name: str | None = None,
	recipient_user: str | None = None,
	limit: int = 200,
) -> dict:
	"""Return vaccination notification diagnostics for local support."""
	item_filters = {"event_key": ["in", ["vaccination_due", "vaccination_overdue"]]}
	if vaccination_record_name:
		item_filters["reference_name"] = vaccination_record_name
	if recipient_user:
		item_filters["recipient_user"] = recipient_user

	items = frappe.get_all(
		"Veterinary Notification Item",
		filters=item_filters,
		fields=[
			"name",
			"idempotency_key",
			"recipient_user",
			"notification_title",
			"reference_doctype",
			"reference_name",
			"action_url",
			"frappe_notification_log",
			"creation",
		],
		order_by="creation desc",
		limit_page_length=limit,
	)

	rows = []
	for item in items:
		native_filters = {
			"for_user": item.get("recipient_user"),
			"subject": item.get("notification_title"),
			"document_type": item.get("reference_doctype"),
			"document_name": item.get("reference_name"),
		}
		if item.get("action_url"):
			native_filters["link"] = item.get("action_url")
		native_logs = frappe.get_all(
			"Notification Log",
			filters=native_filters,
			fields=["name", "for_user", "subject", "document_type", "document_name", "link", "read", "creation"],
			order_by="creation desc",
			limit_page_length=limit,
		)
		rows.append(
			{
				"notification_item": item,
				"matching_native_log_count": len(native_logs),
				"matching_native_logs": native_logs,
			}
		)

	# Fetch recipients for the vaccination record if provided
	recipients = []
	due_date = None
	if vaccination_record_name and frappe.db.exists(VACCINATION_RECORD_DOCTYPE, vaccination_record_name):
		doc = frappe.get_doc(VACCINATION_RECORD_DOCTYPE, vaccination_record_name)
		recipients = resolve_vaccination_notification_recipients(doc)
		due_date = cstr(doc.get("next_due_date"))

	return {
		"vaccination_record": vaccination_record_name,
		"due_date": due_date,
		"recipients": recipients,
		"veterinary_notification_item_count": len(items),
		"rows": rows,
	}


def _vaccination_notifications_available() -> bool:
	return bool(
		frappe.db.exists("DocType", VACCINATION_RECORD_DOCTYPE)
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


def _log_vaccination_notification_error(event_key: str, doc) -> None:
	if not getattr(frappe, "log_error", None):
		return
	try:
		frappe.log_error(
			title="Veterinary Vaccination Notification Failed",
			message=f"Could not create {event_key} notification for {doc.get('name')}.",
		)
	except Exception:
		pass
