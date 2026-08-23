from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.grooming import handle_grooming_session_on_update, validate_grooming_session


class PetGroomingSession(Document):
	def validate(self) -> None:
		if self.get("veterinary_appointment"):
			from vetedge.services.appointment_grooming_bridge import validate_veterinary_appointment_grooming_session

			validate_veterinary_appointment_grooming_session(self)
			return
		validate_grooming_session(self)

	def on_update(self) -> None:
		handle_grooming_session_on_update(self)
		if self.get("veterinary_appointment"):
			from vetedge.services.appointment_grooming_bridge import sync_veterinary_appointment_from_grooming_session

			sync_veterinary_appointment_from_grooming_session(self)
