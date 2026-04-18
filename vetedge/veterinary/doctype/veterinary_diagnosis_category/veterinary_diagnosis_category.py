from __future__ import annotations

from frappe.model.document import Document


class VeterinaryDiagnosisCategory(Document):
	def validate(self) -> None:
		self.category_name = (self.category_name or "").strip()

