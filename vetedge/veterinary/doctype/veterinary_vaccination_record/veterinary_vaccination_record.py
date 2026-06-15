from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.appointment_flow import sync_next_vaccination_appointment_from_record
from vetedge.services.vaccination import validate_vaccination_record


class VeterinaryVaccinationRecord(Document):
	def validate(self) -> None:
		validate_vaccination_record(self)

	def after_insert(self) -> None:
		sync_next_vaccination_appointment_from_record(self)

	def on_update(self) -> None:
		sync_next_vaccination_appointment_from_record(self)
