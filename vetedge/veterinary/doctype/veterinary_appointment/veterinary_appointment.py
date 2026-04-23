from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.copy_control import reset_vetedge_copy_state
from vetedge.services.appointment_flow import validate_appointment
from vetedge.services.notifications import notify_appointment_event


class VeterinaryAppointment(Document):
	def validate(self) -> None:
		reset_vetedge_copy_state(self)
		validate_appointment(self)

	def after_insert(self) -> None:
		notify_appointment_event(self, "appointment_created")

	def on_update(self) -> None:
		previous = self.get_doc_before_save()
		if not previous or previous.status == self.status:
			return

		if self.status == "Confirmed":
			notify_appointment_event(self, "appointment_confirmed")
		elif self.status == "Rescheduled":
			notify_appointment_event(self, "appointment_rescheduled")
		elif self.status == "Cancelled":
			notify_appointment_event(self, "appointment_cancelled")
