from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.consultation_flow import (
	claim_linked_appointment_for_consultation,
	sync_service_appointment_status_from_consultation,
	validate_consultation,
)


class VeterinaryConsultation(Document):
	def validate(self) -> None:
		validate_consultation(self)

	def after_insert(self) -> None:
		claim_linked_appointment_for_consultation(self)
		sync_service_appointment_status_from_consultation(self)

	def on_update(self) -> None:
		sync_service_appointment_status_from_consultation(self)
