from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.grooming import handle_grooming_session_on_update, validate_grooming_session


class PetGroomingSession(Document):
	def validate(self) -> None:
		validate_grooming_session(self)

	def on_update(self) -> None:
		handle_grooming_session_on_update(self)
