from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.consultation_flow import validate_consultation


class VeterinaryConsultation(Document):
	def validate(self) -> None:
		validate_consultation(self)
