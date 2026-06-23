from __future__ import annotations

import frappe
from frappe.utils import cstr

from vetedge.services.notifications import (
	create_notification_item,
	get_role_recipients,
	get_user_recipient,
)
from vetedge.services.permissions import is_internal_staff_user

SUPPORTED_EVENTS = {
	"consultation_awaiting_payment",
	"consultation_sent_to_dispensary",
	"consultation_ready_for_treatment",
	"lab_order_created",
	"lab_sample_collected",
	"lab_result_entered",
	"lab_result_ready_for_review",
	"dispensary_confirmation_completed",
	"dispensary_stock_issue_failed",
	"dispensary_expired_stock_blocked",
	"dispensary_insufficient_non_expired_stock",
}

NOTIFICATION_CONFIGS = {
	"consultation_awaiting_payment": {
		"title": "Veterinary Consultation Awaiting Payment",
		"category": "Consultation",
		"priority": "Normal",
	},
	"consultation_sent_to_dispensary": {
		"title": "Veterinary Consultation Sent to Dispensary",
		"category": "Dispensary",
		"priority": "Normal",
	},
	"consultation_ready_for_treatment": {
		"title": "Veterinary Consultation Ready for Treatment",
		"category": "Consultation",
		"priority": "Normal",
	},
	"lab_order_created": {
		"title": "Veterinary Lab Order Created",
		"category": "Lab",
		"priority": "Normal",
	},
	"lab_sample_collected": {
		"title": "Veterinary Lab Sample Collected",
		"category": "Lab",
		"priority": "Normal",
	},
	"lab_result_entered": {
		"title": "Veterinary Lab Result Entered",
		"category": "Lab",
		"priority": "Normal",
	},
	"lab_result_ready_for_review": {
		"title": "Veterinary Lab Result Ready for Review",
		"category": "Lab",
		"priority": "High",
	},
	"dispensary_confirmation_completed": {
		"title": "Veterinary Dispensary Confirmation Completed",
		"category": "Dispensary",
		"priority": "Normal",
	},
	"dispensary_stock_issue_failed": {
		"title": "Veterinary Dispensary Stock Issue Failed",
		"category": "Dispensary",
		"priority": "High",
	},
	"dispensary_expired_stock_blocked": {
		"title": "Veterinary Dispensary Expired Stock Blocked",
		"category": "Dispensary",
		"priority": "High",
	},
	"dispensary_insufficient_non_expired_stock": {
		"title": "Veterinary Dispensary Insufficient Stock",
		"category": "Dispensary",
		"priority": "High",
	},
}


def handle_clinical_lab_pharmacy_notifications(
	event_key: str,
	reference_doctype: str,
	reference_name: str,
	recipients: list[dict],
	context: dict,
) -> list[dict]:
	if event_key not in SUPPORTED_EVENTS:
		return []

	config = NOTIFICATION_CONFIGS.get(event_key)
	if not config:
		return []

	results = []
	resolved_recipients = resolve_recipients(event_key, reference_doctype, reference_name, context, recipients)

	for recipient_user in resolved_recipients:
		idempotency_key = build_idempotency_key(event_key, reference_doctype, reference_name, recipient_user, context)
		message = build_message(event_key, reference_name, context)
		action_url = get_action_url(reference_doctype, reference_name)

		results.append(
			create_notification_item(
				event_key=event_key,
				recipient_user=recipient_user,
				notification_title=config["title"],
				message=message,
				reference_doctype=reference_doctype,
				reference_name=reference_name,
				action_url=action_url,
				priority=config["priority"],
				payload={
					"category": config["category"],
					"patient": context.get("patient"),
					"primary_owner": context.get("primary_owner"),
					"branch": context.get("branch") or context.get("service_branch"),
					**context,
				},
				idempotency_key=idempotency_key,
			)
		)

	return results


def resolve_recipients(
	event_key: str,
	reference_doctype: str,
	reference_name: str,
	context: dict,
	explicit_recipients: list[dict],
) -> list[str]:
	recipients = []
	branch = context.get("branch") or context.get("service_branch")

	# Fetch document details to find practitioner and owner if they aren't explicitly provided
	try:
		doc = frappe.get_doc(reference_doctype, reference_name)
	except Exception:
		doc = None

	if doc:
		# Add practitioner/creator
		practitioner = None
		if reference_doctype == "Veterinary Consultation":
			practitioner = doc.get("consulting_practitioner")
		elif reference_doctype == "Veterinary Lab Order":
			practitioner = doc.get("requested_by")
		
		if practitioner:
			rec = get_user_recipient(practitioner, audience_type="Internal Staff")
			if rec and rec.get("user"):
				recipients.append(rec["user"])
				
		owner = doc.get("owner")
		if owner:
			rec = get_user_recipient(owner, audience_type="Internal Staff")
			if rec and rec.get("user"):
				recipients.append(rec["user"])

	# Add any explicit recipients passed in the event
	for r in explicit_recipients or []:
		if r.get("user"):
			recipients.append(r["user"])
		elif r.get("identifier"):
			recipients.append(r["identifier"])

	# Add role recipients based on the event key / role mapping
	roles_to_notify = set()
	if event_key in {"lab_order_created", "lab_sample_collected", "lab_result_entered"}:
		roles_to_notify = {"Lab Technician", "VetEdge Lab Technician", "Veterinary Nurse", "VetEdge Doctor"}
	elif event_key == "lab_result_ready_for_review":
		roles_to_notify = {"VetEdge Doctor"}
	elif event_key == "consultation_awaiting_payment":
		roles_to_notify = {"Accounts Manager", "Accounts User", "Accounts/Cashier", "VetEdge Accounts/Cashier", "VetEdge Front Desk", "Branch Manager", "VetEdge Branch Manager"}
	elif event_key in {"consultation_sent_to_dispensary", "dispensary_stock_issue_failed", "dispensary_expired_stock_blocked", "dispensary_insufficient_non_expired_stock"}:
		roles_to_notify = {"Dispensary User", "VetEdge Dispensary User", "Branch Manager", "VetEdge Branch Manager"}
	elif event_key in {"consultation_ready_for_treatment", "dispensary_confirmation_completed"}:
		roles_to_notify = {"VetEdge Doctor", "Veterinary Nurse", "VetEdge Nurse"}

	if roles_to_notify:
		for rec in get_role_recipients(roles_to_notify, branch=branch, audience_type="Internal Staff"):
			if rec.get("user"):
				recipients.append(rec["user"])

	# De-duplicate recipients and ensure no customer/owner/portal owner user is included
	valid_recipients = []
	seen = set()
	for user in recipients:
		user = cstr(user).strip()
		if user and user not in seen:
			seen.add(user)
			if is_internal_staff_user(user):
				valid_recipients.append(user)

	return valid_recipients


def build_message(event_key: str, reference_name: str, context: dict) -> str:
	patient = context.get("patient") or ""
	item_code = context.get("item") or ""
	
	if event_key == "consultation_awaiting_payment":
		return f"Veterinary consultation {reference_name} is awaiting payment for patient {patient}."
	elif event_key == "consultation_sent_to_dispensary":
		return f"Veterinary consultation {reference_name} has been sent to dispensary for patient {patient}."
	elif event_key == "consultation_ready_for_treatment":
		return f"Veterinary consultation {reference_name} is ready for treatment for patient {patient}."
	elif event_key == "lab_order_created":
		return f"Veterinary lab order {reference_name} has been created for patient {patient}."
	elif event_key == "lab_sample_collected":
		return f"Veterinary lab sample has been collected for lab order {reference_name}."
	elif event_key == "lab_result_entered":
		return f"Veterinary lab result has been entered for lab order {reference_name}."
	elif event_key == "lab_result_ready_for_review":
		return f"Veterinary lab results for order {reference_name} are ready for clinical review."
	elif event_key == "dispensary_confirmation_completed":
		return f"Veterinary dispensary confirmation completed for consultation {reference_name}."
	elif event_key == "dispensary_stock_issue_failed":
		return f"Veterinary dispensary stock issue failed for consultation {reference_name}."
	elif event_key == "dispensary_expired_stock_blocked":
		msg = f"Expired stock blocked dispensary action for consultation {reference_name}."
		if item_code:
			msg += f" Item: {item_code}."
		return msg
	elif event_key == "dispensary_insufficient_non_expired_stock":
		msg = f"Insufficient non-expired stock for consultation {reference_name}."
		if item_code:
			msg += f" Item: {item_code}."
		return msg
	return f"Veterinary notification for {reference_name}."


def build_idempotency_key(
	event_key: str,
	reference_doctype: str,
	reference_name: str,
	recipient_user: str,
	context: dict,
) -> str:
	STOCK_FAILURES = {
		"dispensary_stock_issue_failed",
		"dispensary_expired_stock_blocked",
		"dispensary_insufficient_non_expired_stock",
		"stock_issue_failed",
		"expired_stock_blocked",
		"insufficient_non_expired_stock",
	}
	if event_key in STOCK_FAILURES:
		item_code = context.get("item") or ""
		warehouse = context.get("warehouse") or ""
		return f"{event_key}::{reference_doctype}::{reference_name}::{item_code}::{warehouse}::{recipient_user}"
	return f"{event_key}::{reference_doctype}::{reference_name}::{recipient_user}"


def get_action_url(reference_doctype: str, reference_name: str) -> str:
	if reference_doctype == "Veterinary Consultation":
		return f"/app/veterinary-consultation/{reference_name}"
	if reference_doctype == "Veterinary Lab Order":
		return f"/app/veterinary-lab-order/{reference_name}"
	return f"/app/{reference_doctype.lower().replace(' ', '-')}/{reference_name}"
