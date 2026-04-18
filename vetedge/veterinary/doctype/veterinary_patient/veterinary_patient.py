from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.patient import validate_patient
from vetedge.services.registration_billing import handle_patient_registration_insert


class VeterinaryPatient(Document):
	def validate(self) -> None:
		validate_patient(self)

	def after_insert(self) -> None:
		handle_patient_registration_insert(self)
