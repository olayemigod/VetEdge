from __future__ import annotations

import frappe
from frappe.model.document import Document

from vetedge.services.copy_control import reset_vetedge_copy_state
from vetedge.services.appointment_notifications import (
	notify_appointment_checked_in,
	notify_appointment_completed,
)
from vetedge.services.notifications import notify_appointment_event


def validate_appointment(*args, **kwargs):
	from vetedge.services.appointment_flow import validate_appointment as _validate_appointment
	return _validate_appointment(*args, **kwargs)


def sync_missed_appointment_from_source(*args, **kwargs):
	from vetedge.services.appointment_flow import sync_missed_appointment_from_source as _sync_missed_appointment_from_source
	return _sync_missed_appointment_from_source(*args, **kwargs)


class VeterinaryAppointment(Document):
	def validate(self) -> None:
		reset_vetedge_copy_state(self)
		validate_appointment(self)

	def after_insert(self) -> None:
		notify_appointment_event(self, "appointment_created")

	def on_update(self) -> None:
		previous = self.get_doc_before_save()
		sync_missed_appointment_from_source(self)
		if not previous or previous.status == self.status:
			return

		if self.status == "Confirmed":
			notify_appointment_event(self, "appointment_confirmed")
		elif self.status == "Rescheduled":
			notify_appointment_event(self, "appointment_rescheduled")
		elif self.status == "Cancelled":
			notify_appointment_event(self, "appointment_cancelled")
		elif self.status == "Checked In":
			notify_appointment_checked_in(self)
		elif self.status == "Completed":
			notify_appointment_completed(self)

		STATUS_SMS_SETTINGS_MAP = {
			"Owner Requested": "appointment_sms_on_owner_requested",
			"Scheduled": "appointment_sms_on_scheduled",
			"Confirmed": "appointment_sms_on_confirmed",
			"Rescheduled": "appointment_sms_on_rescheduled",
			"Cancelled": "appointment_sms_on_cancelled",
			"Completed": "appointment_sms_on_completed",
			"No Show": "appointment_sms_on_no_show",
		}
		if self.status in STATUS_SMS_SETTINGS_MAP:
			try:
				settings = frappe.get_single("Veterinary Settings")
				if settings.get("enable_notifications") and settings.get("enable_appointment_sms_notifications"):
					setting_field = STATUS_SMS_SETTINGS_MAP[self.status]
					if settings.get(setting_field) and self.primary_owner:
						phone = frappe.db.get_value("Customer", self.primary_owner, "mobile_no") or frappe.db.get_value("Customer", self.primary_owner, "phone")
						if phone:
							tenant = None
							try:
								from vetedge.coreedge_adapter import get_current_vetedge_context
								ctx = get_current_vetedge_context()
								tenant = ctx.get("tenant")
							except Exception:
								pass

							if not tenant:
								try:
									tenant = frappe.db.get_value("CoreEdge Tenant", {}, "name")
								except Exception:
									pass

							from vetedge.services.coreedge_sms import send_sms_safe
							msg = f"Your appointment {self.name} is now {self.status}."
							send_sms_safe(
								to=phone,
								message=msg,
								reference_doctype="Veterinary Appointment",
								reference_name=self.name,
								event="appointment_status_change",
								product_app="VetEdge",
								priority="Normal",
								route_type="Normal",
								tenant=tenant,
								idempotency_key=f"VetEdge:Veterinary Appointment:{self.name}:appointment_status:{self.status}"
							)
			except Exception:
				if getattr(frappe, "log_error", None):
					try:
						frappe.log_error(
							title="Appointment Status SMS Failed",
							message=frappe.get_traceback(),
						)
					except Exception:
						pass
