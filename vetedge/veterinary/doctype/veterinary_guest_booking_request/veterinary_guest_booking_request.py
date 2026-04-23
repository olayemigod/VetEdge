from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.copy_control import reset_vetedge_copy_state
from vetedge.services.guest_booking import validate_guest_booking_request


class VeterinaryGuestBookingRequest(Document):
	def validate(self) -> None:
		reset_vetedge_copy_state(self)
		validate_guest_booking_request(self)
