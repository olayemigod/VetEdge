from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.boarding import validate_pet_boarding_stay


class PetBoardingStay(Document):
	def validate(self) -> None:
		validate_pet_boarding_stay(self)
