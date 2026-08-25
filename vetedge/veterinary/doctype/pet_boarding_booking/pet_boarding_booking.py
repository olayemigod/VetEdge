from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.boarding import validate_pet_boarding_booking
from vetedge.services.boarding_billing_release_safety import validate_boarding_checkout_release_safety
from vetedge.services.boarding_cancellation_safety import enforce_boarding_cancellation_safety


class PetBoardingBooking(Document):
	def validate(self) -> None:
		enforce_boarding_cancellation_safety(self)
		validate_pet_boarding_booking(self)
		if self.status == "Checked Out":
			validate_boarding_checkout_release_safety(self)
