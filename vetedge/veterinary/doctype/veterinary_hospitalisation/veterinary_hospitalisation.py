from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.branch_integrity import enforce_branch_integrity
from vetedge.services.hospitalisation import validate_hospitalisation
from vetedge.services.hospitalisation_context import resolve_hospitalisation_context
from vetedge.services.hospitalisation_form_integrity import enforce_hospitalisation_form_integrity
from vetedge.services.hospitalisation_permissions import validate_hospitalisation_branch_access
from vetedge.services.permissions import validate_doctor_user
from vetedge.services.practitioner_integrity import enforce_practitioner_integrity


class VeterinaryHospitalisation(Document):
	def validate(self) -> None:
		resolve_hospitalisation_context(self)
		enforce_branch_integrity(self)
		validate_hospitalisation_branch_access(self)
		enforce_practitioner_integrity(self)
		validate_doctor_user(self.attending_veterinarian, label="Attending Veterinarian")
		enforce_hospitalisation_form_integrity(self)
		validate_hospitalisation(self)