from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class VeterinaryNotificationItem(Document):
	def validate(self) -> None:
		if not self.recipient_user:
			frappe.throw("Recipient User is required.", frappe.ValidationError)
		if not self.notification_title:
			frappe.throw("Notification Title is required.", frappe.ValidationError)

		self.notification_title = self.notification_title.strip()
		self.status = self.status or "Unread"
		timestamp_fields = {
			"Read": "read_on",
			"Acknowledged": "acknowledged_on",
			"Done": "completed_on",
			"Dismissed": "dismissed_on",
			"Archived": "archived_on",
		}
		timestamp_field = timestamp_fields.get(self.status)
		if timestamp_field and not self.get(timestamp_field):
			self.set(timestamp_field, now_datetime())

