from __future__ import annotations

from frappe.model.document import Document


class VeterinaryDiagnosis(Document):
	def validate(self) -> None:
		self.diagnosis_name = (self.diagnosis_name or "").strip()

