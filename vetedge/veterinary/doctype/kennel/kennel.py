from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.boarding import validate_kennel


class Kennel(Document):
	def validate(self) -> None:
		validate_kennel(self)
