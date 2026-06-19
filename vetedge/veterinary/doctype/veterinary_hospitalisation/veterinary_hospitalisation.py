from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.hospitalisation import validate_hospitalisation


class VeterinaryHospitalisation(Document):
	def validate(self) -> None:
		validate_hospitalisation(self)
