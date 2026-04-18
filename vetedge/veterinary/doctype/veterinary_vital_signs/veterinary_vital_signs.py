from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.vitals import validate_vital_signs


class VeterinaryVitalSigns(Document):
	def validate(self) -> None:
		validate_vital_signs(self)
