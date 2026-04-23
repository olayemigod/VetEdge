from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.treatment_items import validate_treatment_item_profile


class VeterinaryTreatmentItem(Document):
	def validate(self) -> None:
		validate_treatment_item_profile(self)
