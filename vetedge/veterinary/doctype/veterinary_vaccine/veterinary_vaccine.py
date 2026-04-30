from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.vaccination import validate_vaccine


class VeterinaryVaccine(Document):
	def validate(self) -> None:
		validate_vaccine(self)
