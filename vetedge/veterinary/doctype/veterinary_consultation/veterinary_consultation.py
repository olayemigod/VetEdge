from __future__ import annotations

import frappe
from frappe.model.document import Document

from vetedge.services.copy_control import reset_vetedge_copy_state
from vetedge.services.consultation_flow import (
	claim_linked_appointment_for_consultation,
	sync_service_appointment_status_from_consultation,
	validate_consultation,
)
from vetedge.services.billing_core import get_consultation_payment_status


SERVICE_ONLY_APPOINTMENT_TYPES = {"Grooming", "Boarding"}


def sync_follow_up_appointment_from_consultation(*args, **kwargs):
	from vetedge.services.appointment_flow import (
		sync_follow_up_appointment_from_consultation as _sync_follow_up_appointment_from_consultation,
	)

	return _sync_follow_up_appointment_from_consultation(*args, **kwargs)


class VeterinaryConsultation(Document):
	def validate(self) -> None:
		reset_vetedge_copy_state(self)
		validate_linked_appointment_service_type(self)
		set_default_consultation_type(self)
		normalize_consultation_payment_status_fields(self)
		validate_treatment_rows_have_erpnext_item(self)
		validate_consultation(self)

	def after_insert(self) -> None:
		claim_linked_appointment_for_consultation(self)
		sync_service_appointment_status_from_consultation(self)
		sync_follow_up_appointment_from_consultation(self)

	def on_update(self) -> None:
		sync_service_appointment_status_from_consultation(self)
		sync_follow_up_appointment_from_consultation(self)


def validate_linked_appointment_service_type(doc) -> None:
	appointment = doc.get("linked_appointment")
	if not appointment:
		return
	appointment_type = frappe.db.get_value("Veterinary Appointment", appointment, "appointment_type")
	if appointment_type in SERVICE_ONLY_APPOINTMENT_TYPES:
		frappe.throw(
			f"{appointment_type} appointments do not create Veterinary Consultations. Use the {appointment_type} service workflow instead.",
			frappe.ValidationError,
		)


def validate_treatment_rows_have_erpnext_item(doc) -> None:
	for row in doc.get("planned_treatments") or []:
		if row.get("item"):
			continue
		label = row.get("description") or row.get("source_detail_name") or row.get("source_type") or "Treatment"
		frappe.throw(
			f"ERPNext Item is required for Treatment Plan row {label}. Configure the originating master before adding the service to a Consultation.",
			frappe.ValidationError,
		)


def normalize_consultation_payment_status_fields(doc) -> None:
	doc.payment_status = get_consultation_payment_status(doc.get("payment_status"))
	for row in doc.get("planned_treatments") or []:
		if row.get("payment_status"):
			row.payment_status = get_consultation_payment_status(row.get("payment_status"))


def set_default_consultation_type(doc) -> None:
	if not doc.get("consultation_type"):
		doc.consultation_type = "General Consultation"
