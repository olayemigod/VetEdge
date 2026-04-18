from __future__ import annotations

from frappe.model.document import Document


class VeterinaryTreatmentType(Document):
	def validate(self) -> None:
		self.treatment_type_name = (self.treatment_type_name or "").strip()

