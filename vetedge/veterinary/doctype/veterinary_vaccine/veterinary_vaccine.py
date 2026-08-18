from __future__ import annotations

import frappe
from frappe.model.document import Document

from vetedge.services.master_pricing import sync_master_item_price
from vetedge.services.vaccination import validate_vaccine


class VeterinaryVaccine(Document):
	def validate(self) -> None:
		if not self.get("default_item"):
			frappe.throw(
				"Default Item is required. Every Veterinary Vaccine must map to an ERPNext Item for accounting, billing and stock truth.",
				frappe.ValidationError,
			)
		validate_vaccine(self)

	def on_update(self) -> None:
		sync_master_item_price(self, item_field="default_item", price_field="default_price")
