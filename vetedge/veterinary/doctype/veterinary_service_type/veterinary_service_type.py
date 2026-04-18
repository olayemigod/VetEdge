from __future__ import annotations

from frappe.model.document import Document


class VeterinaryServiceType(Document):
	def validate(self) -> None:
		self.service_type_name = (self.service_type_name or "").strip()

