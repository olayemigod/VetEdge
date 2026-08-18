from __future__ import annotations

import frappe
from frappe.model.document import Document

from vetedge.services.lab import validate_lab_test
from vetedge.services.master_pricing import sync_master_item_price


class VeterinaryLabTest(Document):
	def validate(self) -> None:
		if not self.get("linked_item"):
			frappe.throw(
				"Linked Billing Item is required. Every Veterinary Lab Test must map to an ERPNext Item for accounting and billing truth.",
				frappe.ValidationError,
			)
		validate_lab_test(self)

	def on_update(self) -> None:
		sync_master_item_price(self, item_field="linked_item", price_field="default_rate")
