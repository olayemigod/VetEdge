from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.copy_control import reset_vetedge_copy_state
from vetedge.services.consultation_flow import (
	claim_linked_appointment_for_consultation,
	sync_service_appointment_status_from_consultation,
	validate_consultation,
)
from vetedge.services.billing_core import get_consultation_payment_status


class VeterinaryConsultation(Document):
	def validate(self) -> None:
		reset_vetedge_copy_state(self)
		set_default_consultation_type(self)
		normalize_consultation_payment_status_fields(self)
		validate_consultation(self)

	def after_insert(self) -> None:
		claim_linked_appointment_for_consultation(self)
		sync_service_appointment_status_from_consultation(self)

	def on_update(self) -> None:
		sync_service_appointment_status_from_consultation(self)


def normalize_consultation_payment_status_fields(doc) -> None:
	doc.payment_status = get_consultation_payment_status(doc.get("payment_status"))
	for row in doc.get("planned_treatments") or []:
		if row.get("payment_status"):
			row.payment_status = get_consultation_payment_status(row.get("payment_status"))


def set_default_consultation_type(doc) -> None:
	if not doc.get("consultation_type"):
		doc.consultation_type = "General Consultation"
