from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.master_pricing import sync_master_item_price
from vetedge.services.treatment_items import validate_treatment_item_profile


class VeterinaryTreatmentItem(Document):
	def validate(self) -> None:
		validate_treatment_item_profile(self)

	def on_update(self) -> None:
		sync_master_item_price(self, item_field="item", price_field="default_price")
