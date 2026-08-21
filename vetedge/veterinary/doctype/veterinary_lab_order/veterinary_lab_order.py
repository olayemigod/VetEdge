from __future__ import annotations

import frappe
from frappe.model.document import Document

from vetedge.services.lab import handle_lab_order_after_insert, handle_lab_order_on_update, validate_lab_order
from vetedge.services.lab_cancellation import enforce_lab_order_cancellation, enforce_lab_order_delete


class VeterinaryLabOrder(Document):
	def validate(self) -> None:
		validate_lab_order(self)
		enforce_lab_order_cancellation(self)
		for row in self.get("lab_tests") or []:
			if not row.get("billing_item"):
				frappe.throw(
					f"Lab Test {row.get('lab_test_name') or row.get('lab_test_template')} has no ERPNext billing Item. Configure Linked Billing Item on the Veterinary Lab Test master before using it.",
					frappe.ValidationError,
				)
		from vetedge.services.consultation_related_records import validate_consultation_lab_test_duplicates

		validate_consultation_lab_test_duplicates(self)

	def after_insert(self) -> None:
		handle_lab_order_after_insert(self)

	def on_update(self) -> None:
		if self.status == "Cancelled":
			return
		handle_lab_order_on_update(self)

	def on_trash(self) -> None:
		enforce_lab_order_delete(self)
