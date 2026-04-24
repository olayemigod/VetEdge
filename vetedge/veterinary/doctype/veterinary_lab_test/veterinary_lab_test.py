from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.lab import validate_lab_test


class VeterinaryLabTest(Document):
	def validate(self) -> None:
		validate_lab_test(self)
