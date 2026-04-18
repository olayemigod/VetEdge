from __future__ import annotations

from frappe.model.document import Document


class VeterinarySpecies(Document):
	def validate(self) -> None:
		self.species_name = (self.species_name or "").strip()

