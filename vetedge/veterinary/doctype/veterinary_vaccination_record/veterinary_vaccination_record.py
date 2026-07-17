from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.vaccination import validate_vaccination_record


def sync_next_vaccination_appointment_from_record(*args, **kwargs):
	from vetedge.services.appointment_flow import sync_next_vaccination_appointment_from_record as _sync_next_vaccination_appointment_from_record
	return _sync_next_vaccination_appointment_from_record(*args, **kwargs)


class VeterinaryVaccinationRecord(Document):
	def validate(self) -> None:
		validate_vaccination_record(self)

	def after_insert(self) -> None:
		from vetedge.services.consultation_billing_plan import sync_vaccination_to_consultation_plan

		sync_vaccination_to_consultation_plan(self)
		sync_next_vaccination_appointment_from_record(self)

	def on_update(self) -> None:
		from vetedge.services.consultation_billing_plan import sync_vaccination_to_consultation_plan

		sync_vaccination_to_consultation_plan(self)
		sync_next_vaccination_appointment_from_record(self)
