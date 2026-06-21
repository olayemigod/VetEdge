from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import cint


class VeterinaryCareLocation(Document):
	def validate(self) -> None:
		if cint(self.capacity) <= 0:
			frappe.throw("Care location capacity must be greater than zero.", frappe.ValidationError)
