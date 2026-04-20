from __future__ import annotations

import frappe
from frappe.utils import get_datetime, nowdate

from vetedge.services.appointment_flow import transition_appointment_status
from vetedge.services.notifications import emit_notification_event
from vetedge.services.portal_access import (
	get_owner_context,
	get_owner_patient_names,
	get_portal_settings,
	validate_owner_patient_access,
)


@frappe.whitelist()
def get_owner_portal_dashboard() -> dict:
	owner_context = get_owner_context()
	settings = get_portal_settings()
	if not settings["enable_owner_portal"]:
		frappe.throw("Owner portal is not enabled.", frappe.PermissionError)

	patients = get_owner_pets(owner_context)
	appointments = get_owner_appointments(owner_context)
	invoices = get_owner_invoices(owner_context)
	consultations = get_owner_consultation_summaries(owner_context)

	return {
		"owner_context": owner_context,
		"pets": patients,
		"branches": get_portal_branches(),
		"upcoming_appointments": appointments["upcoming"],
		"appointment_history": appointments["history"],
		"outstanding_invoices": invoices["outstanding"],
		"paid_invoices": invoices["paid"],
		"consultations": consultations,
		"settings": settings,
	}


def get_owner_pets(owner_context: dict | None = None) -> list[dict]:
	owner_context = owner_context or get_owner_context()
	customers = owner_context.get("customers", [])
	if not customers:
		return []

	return frappe.get_all(
		"Veterinary Patient",
		filters={"primary_owner": ["in", customers]},
		fields=["name", "patient_name", "species", "breed", "status", "default_branch"],
		order_by="patient_name asc",
	)


def get_owner_appointments(owner_context: dict | None = None) -> dict[str, list[dict]]:
	patients = get_owner_patient_names(owner_context)
	if not patients:
		return {"upcoming": [], "history": []}

	fields = [
		"name",
		"appointment_title",
		"patient",
		"branch",
		"practitioner_name",
		"appointment_datetime",
		"status",
		"appointment_type",
	]
	today_start = f"{nowdate()} 00:00:00"
	upcoming = frappe.get_all(
		"Veterinary Appointment",
		filters={
			"patient": ["in", patients],
			"appointment_datetime": [">=", today_start],
			"status": ["not in", ["Completed", "Cancelled", "No Show"]],
		},
		fields=fields,
		order_by="appointment_datetime asc",
	)
	history = frappe.get_all(
		"Veterinary Appointment",
		filters={
			"patient": ["in", patients],
			"status": ["in", ["Completed", "Cancelled", "No Show"]],
		},
		fields=fields,
		order_by="appointment_datetime desc",
		limit=50,
	)
	return {"upcoming": upcoming, "history": history}


def get_portal_branches() -> list[dict]:
	return frappe.get_all("Branch", fields=["name"], order_by="name asc")


@frappe.whitelist()
def create_owner_appointment_request(
	patient: str,
	preferred_datetime: str,
	preferred_branch: str | None = None,
	reason_for_visit: str | None = None,
) -> dict:
	owner_context = get_owner_context()
	settings = get_portal_settings()
	if not settings["enable_owner_portal"]:
		frappe.throw("Owner portal is not enabled.", frappe.PermissionError)
	if not preferred_datetime:
		frappe.throw("Preferred Date/Time is required.", frappe.ValidationError)
	appointment_datetime = get_datetime(preferred_datetime.replace("T", " "))

	validate_owner_patient_access(patient, owner_context)
	patient_doc = frappe.db.get_value(
		"Veterinary Patient",
		patient,
		["name", "primary_owner", "default_branch"],
		as_dict=True,
	)
	if not patient_doc:
		frappe.throw("Veterinary Patient not found.", frappe.PermissionError)

	branch = preferred_branch or patient_doc.default_branch
	if not branch:
		frappe.throw("Preferred Branch is required.", frappe.ValidationError)
	if not frappe.db.exists("Branch", branch):
		frappe.throw("Preferred Branch must be a valid Branch.", frappe.ValidationError)

	appointment = frappe.get_doc(
		{
			"doctype": "Veterinary Appointment",
			"patient": patient_doc.name,
			"primary_owner": patient_doc.primary_owner,
			"branch": branch,
			"appointment_datetime": appointment_datetime,
			"status": "Owner Requested",
			"appointment_type": "Consultation",
			"created_from": "Portal",
			"notes": reason_for_visit,
		}
	)
	appointment.insert(ignore_permissions=True)

	emit_notification_event(
		event="appointment_request_received",
		reference_doctype=appointment.doctype,
		reference_name=appointment.name,
		payload={
			"customer": patient_doc.primary_owner,
			"patient": appointment.patient,
			"branch": appointment.branch,
			"appointment_datetime": appointment.appointment_datetime,
		},
	)

	return {
		"name": appointment.name,
		"status": appointment.status,
		"appointment_title": appointment.appointment_title,
		"message": "Appointment request created. The clinic will approve it before it is scheduled.",
	}


def get_owner_invoices(owner_context: dict | None = None) -> dict[str, list[dict]]:
	owner_context = owner_context or get_owner_context()
	customers = owner_context.get("customers", [])
	if not customers:
		return {"outstanding": [], "paid": []}

	fields = ["name", "posting_date", "customer", "status", "outstanding_amount", "grand_total", "currency"]
	outstanding = frappe.get_all(
		"Sales Invoice",
		filters={
			"customer": ["in", customers],
			"docstatus": 1,
			"outstanding_amount": [">", 0],
		},
		fields=fields,
		order_by="posting_date desc",
		limit=50,
	)
	paid = frappe.get_all(
		"Sales Invoice",
		filters={
			"customer": ["in", customers],
			"docstatus": 1,
			"outstanding_amount": ["<=", 0],
		},
		fields=fields,
		order_by="posting_date desc",
		limit=50,
	)
	return {"outstanding": outstanding, "paid": paid}


def get_owner_consultation_summaries(owner_context: dict | None = None) -> list[dict]:
	patients = get_owner_patient_names(owner_context)
	if not patients:
		return []

	return frappe.get_all(
		"Veterinary Consultation",
		filters={"patient": ["in", patients]},
		fields=[
			"name",
			"consultation_title",
			"patient",
			"service_branch",
			"consulting_practitioner_name",
			"consultation_datetime",
			"status",
			"presenting_complaint",
			"treatment_plan_summary",
		],
		order_by="consultation_datetime desc",
		limit=50,
	)


@frappe.whitelist()
def request_owner_appointment_change(appointment: str, action: str, appointment_datetime: str | None = None) -> dict:
	owner_context = get_owner_context()
	settings = get_portal_settings()
	appointment_doc = frappe.get_doc("Veterinary Appointment", appointment)
	validate_owner_patient_access(appointment_doc.patient, owner_context)

	if action == "cancel":
		if not settings["allow_owner_cancel_appointment"]:
			frappe.throw("Owner appointment cancellation is not enabled.", frappe.PermissionError)
		return transition_appointment_status(appointment_doc.name, "Cancelled")

	if action == "reschedule":
		if not settings["allow_owner_reschedule_appointment"]:
			frappe.throw("Owner appointment reschedule is not enabled.", frappe.PermissionError)
		if not appointment_datetime:
			frappe.throw("A new appointment date/time is required.", frappe.ValidationError)
		appointment_doc.appointment_datetime = appointment_datetime
		appointment_doc.status = "Rescheduled"
		appointment_doc.save()
		return {"name": appointment_doc.name, "status": appointment_doc.status}

	frappe.throw(f"Unsupported appointment action: {action}", frappe.ValidationError)
