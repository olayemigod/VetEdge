from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.vaccination import validate_vaccination_record


class VeterinaryVaccinationRecord(Document):
	def validate(self) -> None:
		validate_vaccination_record(self)
