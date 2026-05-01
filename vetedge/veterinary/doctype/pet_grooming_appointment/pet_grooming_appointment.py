from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.grooming import (
	handle_grooming_appointment_after_insert,
	handle_grooming_appointment_on_update,
	validate_grooming_appointment,
)


class PetGroomingAppointment(Document):
	def validate(self) -> None:
		validate_grooming_appointment(self)

	def after_insert(self) -> None:
		handle_grooming_appointment_after_insert(self)

	def on_update(self) -> None:
		handle_grooming_appointment_on_update(self)
