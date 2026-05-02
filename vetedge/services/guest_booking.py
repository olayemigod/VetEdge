from __future__ import annotations

import frappe
from frappe.utils import cint, flt, get_datetime

from vetedge.services.notifications import emit_notification_event
from vetedge.services.payment_service import initiate_payment
from vetedge.services.permissions import can_access_branch_data
from vetedge.services.portal_access import get_portal_settings


GUEST_BOOKING_STATUSES = {
	"Registration Requested",
	"Registration Confirmed",
	"Converted",
	"Cancelled",
}
STAFF_CONVERSION_ROLES = {
	"System Manager",
	"VetEdge Administrator",
	"VetEdge Front Desk",
	"VetEdge Doctor",
}


def validate_guest_booking_request(doc) -> None:
	if not doc.status:
		doc.status = "Registration Requested"

	if doc.status not in GUEST_BOOKING_STATUSES:
		frappe.throw(f"Invalid guest booking status: {doc.status}", frappe.ValidationError)

	for fieldname, label in {
		"guest_name": "Guest Name",
		"pet_name": "Pet Name",
		"species": "Species",
		"preferred_branch": "Preferred Branch",
	}.items():
		if not doc.get(fieldname):
			frappe.throw(f"{label} is required.", frappe.ValidationError)

	if not (doc.guest_email or doc.guest_phone):
		frappe.throw("Guest Email or Guest Phone is required.", frappe.ValidationError)

	if not frappe.db.exists("Branch", doc.preferred_branch):
		frappe.throw("Preferred Branch must be a valid Branch.", frappe.ValidationError)

	if cint(doc.appointment_requested):
		if not doc.preferred_datetime:
			frappe.throw("Preferred Date/Time is required when appointment is requested.", frappe.ValidationError)

		try:
			get_datetime(doc.preferred_datetime)
		except Exception:
			frappe.throw("Preferred Date/Time must be a valid datetime.", frappe.ValidationError)

	if doc.species and not frappe.db.exists("Veterinary Species", doc.species):
		frappe.throw("Species must be a valid Veterinary Species.", frappe.ValidationError)

	if doc.breed and not frappe.db.exists("Veterinary Breed", doc.breed):
		frappe.throw("Breed must be a valid Veterinary Breed.", frappe.ValidationError)

	doc.source = doc.source or "Guest Portal"


@frappe.whitelist(allow_guest=True)
def create_guest_booking_request(**values) -> dict:
	settings = get_portal_settings()
	if not settings["enable_guest_booking"]:
		frappe.throw("Guest booking is not enabled.", frappe.PermissionError)

	doc = frappe.get_doc(
		{
			"doctype": "Veterinary Guest Booking Request",
			"guest_name": values.get("guest_name"),
			"guest_email": values.get("guest_email"),
			"guest_phone": values.get("guest_phone"),
			"pet_name": values.get("pet_name"),
			"species": values.get("species"),
			"breed": values.get("breed"),
			"preferred_branch": values.get("preferred_branch"),
			"appointment_requested": parse_checked(values.get("appointment_requested")),
			"preferred_datetime": values.get("preferred_datetime"),
			"reason_for_visit": values.get("reason_for_visit"),
			"status": "Registration Requested",
			"source": "Guest Portal",
		}
	)
	doc.insert(ignore_permissions=True)

	if doc.appointment_requested:
		appointment = create_awaiting_registration_appointment(doc)
		doc.db_set("linked_appointment", appointment.name, update_modified=False)

	emit_notification_event(
		event_key="registration_request_received",
		reference_doctype=doc.doctype,
		reference_name=doc.name,
		payload={
			"guest_name": doc.guest_name,
			"guest_email": doc.guest_email,
			"guest_phone": doc.guest_phone,
			"pet_name": doc.pet_name,
			"preferred_branch": doc.preferred_branch,
			"preferred_datetime": doc.preferred_datetime,
			"appointment_requested": doc.appointment_requested,
		},
	)
	if doc.appointment_requested:
		emit_notification_event(
			event_key="guest_appointment_request_received",
			reference_doctype=doc.doctype,
			reference_name=doc.name,
			payload={
				"guest_name": doc.guest_name,
				"guest_email": doc.guest_email,
				"guest_phone": doc.guest_phone,
				"pet_name": doc.pet_name,
				"preferred_branch": doc.preferred_branch,
				"preferred_datetime": doc.preferred_datetime,
				"linked_appointment": doc.linked_appointment,
			},
		)

	return {
		"name": doc.name,
		"status": doc.status,
		"linked_appointment": doc.linked_appointment,
		"message": "Registration request received. The clinic team will review it before creating your pet profile.",
	}


def parse_checked(value) -> int:
	return 1 if value in (1, "1", "true", "True", "on", True) else 0


def create_awaiting_registration_appointment(request) -> object:
	appointment = frappe.get_doc(
		{
			"doctype": "Veterinary Appointment",
			"guest_booking_request": request.name,
			"branch": request.preferred_branch,
			"appointment_datetime": request.preferred_datetime,
			"status": "Awaiting Registration",
			"appointment_type": "Consultation",
			"created_from": "Guest",
			"notes": request.reason_for_visit,
		}
	)
	appointment.insert(ignore_permissions=True)
	return appointment


@frappe.whitelist()
def confirm_guest_registration(booking_request: str) -> dict:
	validate_staff_can_convert_booking_request()

	request = frappe.get_doc("Veterinary Guest Booking Request", booking_request)
	validate_staff_can_manage_booking_request(request)
	if request.status in {"Converted", "Cancelled"}:
		frappe.throw(f"Registration request cannot be confirmed while it is {request.status}.")

	if request.linked_patient:
		return build_registration_confirmation_response(request)

	customer = create_customer_from_guest_request(request)
	patient = create_patient_from_guest_request(request, customer.name)

	request.linked_customer = customer.name
	request.linked_patient = patient.name
	request.registration_invoice = patient.registration_invoice
	request.status = "Registration Confirmed"
	request.save()

	move_awaiting_registration_appointment_to_owner_requested(request)

	emit_notification_event(
		event_key="registration_confirmed",
		reference_doctype=request.doctype,
		reference_name=request.name,
		payload={
			"customer": customer.name,
			"patient": patient.name,
			"registration_invoice": patient.registration_invoice,
		},
	)

	return build_registration_confirmation_response(request)


@frappe.whitelist()
def create_appointment_from_booking_request(booking_request: str) -> dict:
	validate_staff_can_convert_booking_request()

	request = frappe.get_doc("Veterinary Guest Booking Request", booking_request)
	validate_staff_can_manage_booking_request(request)
	if request.status in {"Converted", "Cancelled"}:
		frappe.throw(
			f"Booking request cannot be converted while it is {request.status}.",
			frappe.ValidationError,
		)

	if not request.linked_patient:
		frappe.throw(
			"Confirm registration before creating or approving an appointment from this request.",
			frappe.ValidationError,
		)

	if request.linked_appointment:
		appointment = frappe.get_doc("Veterinary Appointment", request.linked_appointment)
		if appointment.status == "Awaiting Registration":
			appointment = move_awaiting_registration_appointment_to_owner_requested(request)
			request.status = "Converted"
			request.save()
			return build_appointment_response(appointment, request)

		frappe.throw("Booking request already has a linked Veterinary Appointment.", frappe.ValidationError)

	appointment = frappe.get_doc(
		{
			"doctype": "Veterinary Appointment",
			"patient": request.linked_patient,
			"branch": request.preferred_branch,
			"appointment_datetime": request.preferred_datetime,
			"status": "Owner Requested",
			"appointment_type": "Consultation",
			"created_from": "Guest",
			"notes": request.reason_for_visit,
		}
	)
	appointment.insert()

	request.linked_appointment = appointment.name
	request.status = "Converted"
	request.save()

	emit_notification_event(
		event_key="appointment_booked",
		reference_doctype=appointment.doctype,
		reference_name=appointment.name,
		payload={
			"booking_request": request.name,
			"patient": appointment.patient,
			"branch": appointment.branch,
			"appointment_datetime": appointment.appointment_datetime,
		},
	)

	return build_appointment_response(appointment, request)


def move_awaiting_registration_appointment_to_owner_requested(request) -> object | None:
	if not request.linked_appointment:
		return None

	appointment = frappe.get_doc("Veterinary Appointment", request.linked_appointment)
	if appointment.status != "Awaiting Registration":
		return appointment

	appointment.patient = request.linked_patient
	appointment.primary_owner = request.linked_customer
	appointment.status = "Owner Requested"
	appointment.save()
	emit_notification_event(
		event_key="guest_appointment_ready_for_approval",
		reference_doctype=appointment.doctype,
		reference_name=appointment.name,
		payload={
			"booking_request": request.name,
			"customer": request.linked_customer,
			"patient": request.linked_patient,
			"branch": appointment.branch,
			"appointment_datetime": appointment.appointment_datetime,
			"status": appointment.status,
		},
	)
	return appointment


def create_customer_from_guest_request(request) -> object:
	customer_group = get_default_customer_group()
	territory = get_default_territory()
	if not customer_group:
		frappe.throw("Set a default Customer Group before confirming guest registrations.")
	if not territory:
		frappe.throw("Set a default Territory before confirming guest registrations.")

	customer = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": request.guest_name,
			"customer_type": "Individual",
			"customer_group": customer_group,
			"territory": territory,
			"mobile_no": request.guest_phone,
			"email_id": request.guest_email,
		}
	)
	customer.insert(ignore_permissions=True)
	return customer


def create_patient_from_guest_request(request, customer: str) -> object:
	patient = frappe.get_doc(
		{
			"doctype": "Veterinary Patient",
			"patient_name": request.pet_name,
			"primary_owner": customer,
			"default_branch": request.preferred_branch,
			"species": request.species,
			"breed": request.breed,
			"status": "Active",
		}
	)
	patient.insert(ignore_permissions=True)
	return frappe.get_doc("Veterinary Patient", patient.name)


def get_default_customer_group() -> str | None:
	customer_group = frappe.db.get_single_value("Selling Settings", "customer_group")
	if customer_group:
		return customer_group

	groups = frappe.get_all("Customer Group", filters={"is_group": 0}, pluck="name", limit=1)
	return groups[0] if groups else None


def get_default_territory() -> str | None:
	territory = frappe.db.get_single_value("Selling Settings", "territory")
	if territory:
		return territory

	territories = frappe.get_all("Territory", filters={"is_group": 0}, pluck="name", limit=1)
	return territories[0] if territories else None


def build_registration_confirmation_response(request) -> dict:
	return {
		"name": request.name,
		"status": request.status,
		"linked_customer": request.linked_customer,
		"linked_patient": request.linked_patient,
		"linked_appointment": request.linked_appointment,
		"registration_invoice": request.registration_invoice,
	}


def build_appointment_response(appointment, request) -> dict:
	return {
		"name": appointment.name if appointment else None,
		"appointment_title": appointment.appointment_title if appointment else None,
		"booking_request": request.name,
		"booking_status": request.status,
	}


@frappe.whitelist(allow_guest=True)
def initiate_guest_registration_payment(
	booking_request: str,
	guest_email: str | None = None,
	guest_phone: str | None = None,
	backend_mode: str | None = None,
	provider: str | None = None,
) -> dict:
	settings = get_portal_settings()
	if not settings["enable_portal_payments"]:
		frappe.throw("Portal payments are not enabled.", frappe.PermissionError)

	request = validate_guest_registration_payment_access(booking_request, guest_email, guest_phone)
	if not request.registration_invoice:
		frappe.throw("Registration invoice is not ready yet. Please check again after the clinic confirms registration.")

	invoice = frappe.get_doc("Sales Invoice", request.registration_invoice)
	if invoice.name != frappe.db.get_value("Veterinary Patient", request.linked_patient, "registration_invoice"):
		frappe.throw("Only registration invoice payments are allowed on the guest page.", frappe.PermissionError)

	if invoice.docstatus != 1:
		frappe.throw("Registration invoice is not submitted yet. Please wait for the clinic to prepare it for payment.")

	if flt(invoice.outstanding_amount) <= 0:
		frappe.throw("This registration invoice has no outstanding amount.")

	return initiate_payment(
		invoice_name=invoice.name,
		access_context={
			"mode": "guest_registration",
			"allowed_invoice": request.registration_invoice,
		},
		source_context={
			"source": "guest_registration",
			"booking_request": request.name,
			"guest_email": request.guest_email,
			"guest_phone": request.guest_phone,
		},
		backend_mode=backend_mode or provider,
	)


def validate_guest_registration_payment_access(
	booking_request: str,
	guest_email: str | None,
	guest_phone: str | None,
) -> object:
	request = frappe.get_doc("Veterinary Guest Booking Request", booking_request)
	if not (guest_email or guest_phone):
		frappe.throw("Email or phone is required to verify this registration request.", frappe.PermissionError)

	if guest_email and request.guest_email and guest_email.strip().lower() == request.guest_email.strip().lower():
		return request

	if guest_phone and request.guest_phone and guest_phone.strip() == request.guest_phone.strip():
		return request

	frappe.throw("Registration request verification failed.", frappe.PermissionError)


def validate_staff_can_convert_booking_request() -> None:
	if STAFF_CONVERSION_ROLES.isdisjoint(set(frappe.get_roles())):
		frappe.throw("Only clinic staff can manage guest registration requests.", frappe.PermissionError)


def validate_staff_can_manage_booking_request(request) -> None:
	can_access_branch_data(frappe.session.user, request.preferred_branch, raise_exception=True)
