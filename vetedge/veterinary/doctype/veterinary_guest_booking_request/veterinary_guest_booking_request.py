from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.guest_booking import validate_guest_booking_request


class VeterinaryGuestBookingRequest(Document):
	def validate(self) -> None:
		validate_guest_booking_request(self)
