from __future__ import annotations

from frappe.utils import now_datetime


def reset_vetedge_copy_state(doc) -> None:
	if not is_copy_operation(doc):
		return

	handlers = {
		"Veterinary Consultation": reset_consultation_copy_state,
		"Veterinary Appointment": reset_appointment_copy_state,
		"Veterinary Guest Booking Request": reset_guest_booking_copy_state,
		"Veterinary Patient": reset_patient_copy_state,
		"Veterinary Vital Signs": reset_vitals_copy_state,
	}
	handler = handlers.get(getattr(doc, "doctype", None))
	if handler:
		handler(doc)


def is_copy_operation(doc) -> bool:
	flags = getattr(doc, "flags", None)
	return bool(getattr(flags, "in_copy", False))


def reset_consultation_copy_state(doc) -> None:
	doc.status = "Draft"
	doc.consultation_datetime = None
	doc.daily_consultation_number = None
	doc.consultation_title = None
	doc.linked_appointment = None
	doc.follow_up_appointment = None
	doc.dispensary_status = "Not Required"
	doc.dispensary_confirmed_on = None
	doc.dispensary_confirmed_by = None
	doc.dispensary_stock_entry = None
	doc.linked_invoice = None
	doc.payment_status = "Not Billed"
	if hasattr(doc, "set"):
		doc.set("dispensed_treatments", [])
	else:
		doc.dispensed_treatments = []


def reset_appointment_copy_state(doc) -> None:
	doc.status = "Scheduled"
	doc.appointment_title = None
	doc.guest_booking_request = None
	doc.created_from = "Manual"
	doc.linked_consultation = None
	doc.reminder_sent = 0
	doc.reminder_sent_on = None


def reset_guest_booking_copy_state(doc) -> None:
	doc.status = "Registration Requested"
	doc.linked_customer = None
	doc.linked_patient = None
	doc.linked_appointment = None
	doc.registration_invoice = None


def reset_patient_copy_state(doc) -> None:
	doc.status = "Active"
	doc.is_deceased = 0
	doc.registration_status = "Registered"
	doc.registration_invoice = None
	doc.registration_billed = 0
	doc.registration_fee_amount = None


def reset_vitals_copy_state(doc) -> None:
	doc.vitals_title = None
	doc.recorded_on = now_datetime()
	doc.recorded_by = None
