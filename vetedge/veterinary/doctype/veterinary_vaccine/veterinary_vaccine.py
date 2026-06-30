from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.master_pricing import sync_master_item_price
from vetedge.services.vaccination import validate_vaccine


class VeterinaryVaccine(Document):
	def validate(self) -> None:
		validate_vaccine(self)

	def on_update(self) -> None:
		sync_master_item_price(self, item_field="default_item", price_field="default_price")
