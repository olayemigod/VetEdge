from __future__ import annotations

import frappe
from frappe.model.document import Document

from vetedge.services.lab import handle_lab_order_after_insert, handle_lab_order_on_update, validate_lab_order
from vetedge.services.lab_cancellation import enforce_lab_order_cancellation, enforce_lab_order_delete


VETERINARY_NOTIFICATION_LOG_DOCTYPE = "Veterinary Notification Log"


def _detach_veterinary_notification_logs(lab_order: str) -> None:
	"""Preserve notification audit rows while clearing the Lab Order reverse link."""
	if not lab_order or not frappe.db.exists("DocType", VETERINARY_NOTIFICATION_LOG_DOCTYPE):
		return
	for row in frappe.get_all(
		VETERINARY_NOTIFICATION_LOG_DOCTYPE,
		filters={"reference_doctype": "Veterinary Lab Order", "reference_name": lab_order},
		fields=["name"],
		limit=500,
	):
		frappe.db.set_value(
			VETERINARY_NOTIFICATION_LOG_DOCTYPE,
			row.name,
			{"reference_doctype": None, "reference_name": None},
			update_modified=False,
		)


class VeterinaryLabOrder(Document):
	def validate(self) -> None:
		validate_lab_order(self)
		# The custom delivery log uses a Dynamic Link back to the Lab Order. Clear
		# that reverse link inside the same transaction before cancellation cleanup
		# so Frappe cannot reject the operation because an audit log points at it.
		# If cancellation is blocked later, the request transaction rolls this back.
		if self.status == "Cancelled":
			_detach_veterinary_notification_logs(self.name)
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
		# Defensive/admin path only. The normal EdgeSuite Lab workflow no longer
		# exposes Delete, but keep reverse-link cleanup safe for controlled cleanup.
		_detach_veterinary_notification_logs(self.name)
		enforce_lab_order_delete(self)
