from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.grooming import validate_grooming_service


class PetGroomingService(Document):
	def validate(self) -> None:
		validate_grooming_service(self)
