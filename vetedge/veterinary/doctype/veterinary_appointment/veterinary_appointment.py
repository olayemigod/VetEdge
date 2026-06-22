from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.copy_control import reset_vetedge_copy_state
from vetedge.services.appointment_notifications import (
	notify_appointment_checked_in,
	notify_appointment_completed,
)
from vetedge.services.notifications import notify_appointment_event


def validate_appointment(*args, **kwargs):
	from vetedge.services.appointment_flow import validate_appointment as _validate_appointment
	return _validate_appointment(*args, **kwargs)


def sync_missed_appointment_from_source(*args, **kwargs):
	from vetedge.services.appointment_flow import sync_missed_appointment_from_source as _sync_missed_appointment_from_source
	return _sync_missed_appointment_from_source(*args, **kwargs)


class VeterinaryAppointment(Document):
	def validate(self) -> None:
		reset_vetedge_copy_state(self)
		validate_appointment(self)

	def after_insert(self) -> None:
		notify_appointment_event(self, "appointment_created")

	def on_update(self) -> None:
		previous = self.get_doc_before_save()
		sync_missed_appointment_from_source(self)
		if not previous or previous.status == self.status:
			return

		if self.status == "Confirmed":
			notify_appointment_event(self, "appointment_confirmed")
		elif self.status == "Rescheduled":
			notify_appointment_event(self, "appointment_rescheduled")
		elif self.status == "Cancelled":
			notify_appointment_event(self, "appointment_cancelled")
		elif self.status == "Checked In":
			notify_appointment_checked_in(self)
		elif self.status == "Completed":
			notify_appointment_completed(self)
