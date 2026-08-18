from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.lab import handle_lab_order_after_insert, handle_lab_order_on_update, validate_lab_order


class VeterinaryLabOrder(Document):
	def validate(self) -> None:
		validate_lab_order(self)
		from vetedge.services.consultation_related_records import validate_consultation_lab_test_duplicates

		validate_consultation_lab_test_duplicates(self)

	def after_insert(self) -> None:
		handle_lab_order_after_insert(self)

	def on_update(self) -> None:
		handle_lab_order_on_update(self)
