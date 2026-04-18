from __future__ import annotations

from frappe.model.document import Document


class VeterinarySymptom(Document):
	def validate(self) -> None:
		self.symptom_name = (self.symptom_name or "").strip()

