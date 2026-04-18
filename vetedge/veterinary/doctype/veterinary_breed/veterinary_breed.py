from __future__ import annotations

import frappe
from frappe.model.document import Document


class VeterinaryBreed(Document):
	def validate(self) -> None:
		self.breed_name = (self.breed_name or "").strip()
		self.validate_unique_species_breed()

	def validate_unique_species_breed(self) -> None:
		if not self.breed_name or not self.species:
			return

		existing = frappe.db.exists(
			"Veterinary Breed",
			{"breed_name": self.breed_name, "species": self.species, "name": ["!=", self.name]},
		)
		if existing:
			frappe.throw("Breed already exists for the selected Species.", frappe.DuplicateEntryError)

