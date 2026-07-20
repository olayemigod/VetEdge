from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.appointment_quick_create_safety import registration_invoice_context
from vetedge.services.copy_control import reset_vetedge_copy_state
from vetedge.services.patient import validate_patient
from vetedge.services.registration_billing import handle_patient_registration_insert


class VeterinaryPatient(Document):
	def validate(self) -> None:
		reset_vetedge_copy_state(self)
		validate_patient(self)

	def after_insert(self) -> None:
		with registration_invoice_context(self):
			handle_patient_registration_insert(self)
