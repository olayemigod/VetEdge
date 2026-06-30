from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.lab import validate_lab_test
from vetedge.services.master_pricing import sync_master_item_price


class VeterinaryLabTest(Document):
	def validate(self) -> None:
		validate_lab_test(self)

	def on_update(self) -> None:
		sync_master_item_price(self, item_field="linked_item", price_field="default_rate")
