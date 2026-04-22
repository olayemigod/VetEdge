from __future__ import annotations

from urllib.parse import quote

import frappe
from frappe.utils import get_datetime, nowdate

from vetedge.services.appointment_flow import emit_appointment_status_notification
from vetedge.install.print_formats import OWNER_INVOICE_PRINT_FORMAT
from vetedge.services.notifications import emit_notification_event
from vetedge.services.portal_access import (
	get_owner_context,
	get_owner_patient_names,
	get_portal_settings,
	validate_owner_appointment_access,
	validate_owner_invoice_access,
	validate_owner_patient_access,
)


@frappe.whitelist()
def get_owner_portal_dashboard() -> dict:
	owner_context = get_owner_context()
	settings = get_portal_settings()
	if not settings["enable_owner_portal"]:
		frappe.throw("Owner portal is not enabled.", frappe.PermissionError)

	owner_profile = get_owner_profile(owner_context)
	patients = get_owner_pets(owner_context)
	appointments = get_owner_appointments(owner_context)
	invoices = get_owner_invoices(owner_context)
	consultations = get_owner_consultation_summaries(owner_context)

	return {
		"owner_context": owner_context,
		"owner_profile": owner_profile,
		"portal_theme": settings.get("portal_theme", get_portal_settings().get("portal_theme", {})),
		"pets": patients,
		"branches": get_portal_branches(),
		"upcoming_appointments": appointments["upcoming"],
		"appointment_history": appointments["history"],
		"outstanding_invoices": invoices["outstanding"],
		"paid_invoices": invoices["paid"],
		"consultations": consultations,
		"settings": settings,
	}


def get_owner_profile(owner_context: dict | None = None) -> dict:
	owner_context = owner_context or get_owner_context()
	customers = owner_context.get("customers", [])
	if not customers:
		return {}

	customer_name = customers[0]
	customer_meta = frappe.get_meta("Customer")
	fields = ["name", "customer_name"]
	for fieldname in ("email_id", "mobile_no", "phone"):
		if customer_meta.has_field(fieldname):
			fields.append(fieldname)

	customer = frappe.db.get_value(
		"Customer",
		customer_name,
		fields,
		as_dict=True,
	)
	if not customer:
		return {}

	return {
		"customer": customer.name,
		"display_name": customer.customer_name or customer.name,
		"email": customer.get("email_id"),
		"phone": customer.get("mobile_no") or customer.get("phone"),
		"account_count": len(customers),
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
		event="owner_appointment_request_received",
		reference_doctype=appointment.doctype,
		reference_name=appointment.name,
		payload={
			"owner_user": owner_context.get("user"),
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
	for invoice in outstanding + paid:
		invoice["download_pdf_url"] = get_owner_invoice_pdf_url(invoice.name)
	return {"outstanding": outstanding, "paid": paid}


def get_owner_consultation_summaries(owner_context: dict | None = None) -> list[dict]:
	patients = get_owner_patient_names(owner_context)
	if not patients:
		return []

	patient_map = {
		row.name: row.patient_name or row.name
		for row in frappe.get_all(
			"Veterinary Patient",
			filters={"name": ["in", patients]},
			fields=["name", "patient_name"],
		)
	}

	rows = frappe.get_all(
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
		],
		order_by="consultation_datetime desc",
		limit=50,
	)
	return [
		{
			**row,
			"patient_name": patient_map.get(row.patient, row.patient),
			"summary_title": row.consultation_title or "Consultation Summary",
		}
		for row in rows
	]


@frappe.whitelist()
def get_owner_invoice(invoice_name: str) -> dict:
	owner_context = get_owner_context()
	invoice = validate_owner_invoice_access(invoice_name, owner_context)
	return {
		"name": invoice.name,
		"customer": invoice.customer,
		"posting_date": invoice.posting_date,
		"status": invoice.status,
		"outstanding_amount": invoice.outstanding_amount,
		"grand_total": invoice.grand_total,
		"currency": invoice.currency,
		"download_pdf_url": get_owner_invoice_pdf_url(invoice.name),
	}


@frappe.whitelist()
def download_owner_invoice_pdf(invoice_name: str, print_format: str | None = None) -> None:
	owner_context = get_owner_context()
	validate_owner_invoice_access(invoice_name, owner_context)
	selected_print_format = print_format or OWNER_INVOICE_PRINT_FORMAT

	try:
		frappe.local.flags.ignore_print_permissions = True
		try:
			pdf_content = generate_owner_invoice_pdf(invoice_name, selected_print_format)
		except (OSError, TimeoutError):
			frappe.throw(
				"Invoice PDF download is not available yet because PDF generation is not configured on this server.",
				frappe.ValidationError,
			)
	finally:
		frappe.local.flags.ignore_print_permissions = False

	frappe.local.response.filename = f"{invoice_name}.pdf"
	frappe.local.response.filecontent = pdf_content
	frappe.local.response.type = "pdf"


def generate_owner_invoice_pdf(invoice_name: str, print_format: str) -> bytes:
	letterhead_name = resolve_invoice_letterhead(invoice_name)
	last_error: Exception | None = None
	for generator in ("chrome", "wkhtmltopdf"):
		try:
			set_request_pdf_generator(generator)
			return frappe.get_print(
				"Sales Invoice",
				invoice_name,
				print_format=print_format,
				as_pdf=True,
				no_letterhead=0,
				letterhead=letterhead_name,
				pdf_generator=generator,
			)
		except (OSError, TimeoutError) as exc:
			last_error = exc
		finally:
			clear_request_pdf_generator()

	if last_error:
		raise last_error

	raise OSError("No PDF generator available.")


def resolve_invoice_letterhead(invoice_name: str) -> str | None:
	invoice = frappe.db.get_value("Sales Invoice", invoice_name, ["letter_head", "company"], as_dict=True)
	if not invoice:
		return None

	if invoice.get("letter_head"):
		return invoice.letter_head

	if invoice.get("company") and frappe.db.has_column("Company", "default_letter_head"):
		company_letterhead = frappe.db.get_value("Company", invoice.company, "default_letter_head")
		if company_letterhead:
			return company_letterhead

	return frappe.db.get_value("Letter Head", {"is_default": 1}, "name")


def set_request_pdf_generator(generator: str) -> None:
	if not hasattr(frappe.local, "form_dict") or frappe.local.form_dict is None:
		frappe.local.form_dict = {}

	form_dict = frappe.local.form_dict
	if isinstance(form_dict, dict):
		form_dict["pdf_generator"] = generator
	else:
		setattr(form_dict, "pdf_generator", generator)


def clear_request_pdf_generator() -> None:
	if not hasattr(frappe.local, "form_dict") or frappe.local.form_dict is None:
		return

	form_dict = frappe.local.form_dict
	if isinstance(form_dict, dict):
		form_dict.pop("pdf_generator", None)
	else:
		if hasattr(form_dict, "pdf_generator"):
			delattr(form_dict, "pdf_generator")


def get_owner_invoice_pdf_url(invoice_name: str) -> str:
	return (
		"/api/method/vetedge.services.owner_portal.download_owner_invoice_pdf"
		f"?invoice_name={quote(invoice_name)}"
	)


@frappe.whitelist()
def request_owner_appointment_change(appointment: str, action: str, appointment_datetime: str | None = None) -> dict:
	owner_context = get_owner_context()
	settings = get_portal_settings()
	validate_owner_appointment_access(appointment, owner_context)
	appointment_doc = frappe.get_doc("Veterinary Appointment", appointment)

	if action == "cancel":
		if not settings["allow_owner_cancel_appointment"]:
			frappe.throw("Owner appointment cancellation is not enabled.", frappe.PermissionError)
		previous_status = appointment_doc.status
		appointment_doc.status = "Cancelled"
		appointment_doc.save(ignore_permissions=True)
		emit_appointment_status_notification(appointment_doc, previous_status, appointment_doc.status)
		return {"name": appointment_doc.name, "status": appointment_doc.status}

	if action == "reschedule":
		if not settings["allow_owner_reschedule_appointment"]:
			frappe.throw("Owner appointment reschedule is not enabled.", frappe.PermissionError)
		if not appointment_datetime:
			frappe.throw("A new appointment date/time is required.", frappe.ValidationError)
		previous_datetime = appointment_doc.appointment_datetime
		previous_status = appointment_doc.status
		appointment_doc.appointment_datetime = appointment_datetime
		appointment_doc.status = "Rescheduled"
		appointment_doc.save(ignore_permissions=True)
		emit_notification_event(
			event="appointment_rescheduled",
			reference_doctype=appointment_doc.doctype,
			reference_name=appointment_doc.name,
			payload={
				"owner_user": owner_context.get("user"),
				"customer": appointment_doc.primary_owner,
				"patient": appointment_doc.patient,
				"branch": appointment_doc.branch,
				"previous_datetime": previous_datetime,
				"appointment_datetime": appointment_doc.appointment_datetime,
				"previous_status": previous_status,
				"status": appointment_doc.status,
			},
		)
		return {"name": appointment_doc.name, "status": appointment_doc.status}

	frappe.throw(f"Unsupported appointment action: {action}", frappe.ValidationError)
