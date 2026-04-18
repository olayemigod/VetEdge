from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class VeterinaryBranchRegistrationRule(Document):
	def validate(self) -> None:
		if self.registration_fee not in (None, "") and flt(self.registration_fee) < 0:
			frappe.throw("Registration Fee cannot be negative.", frappe.ValidationError)

