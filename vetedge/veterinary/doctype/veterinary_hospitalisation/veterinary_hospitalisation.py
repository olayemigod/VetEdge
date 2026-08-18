from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.branch_integrity import enforce_branch_integrity
from vetedge.services.hospitalisation import validate_hospitalisation
from vetedge.services.practitioner_integrity import enforce_practitioner_integrity


class VeterinaryHospitalisation(Document):
	def validate(self) -> None:
		enforce_branch_integrity(self)
		enforce_practitioner_integrity(self)
		validate_hospitalisation(self)
