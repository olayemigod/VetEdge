from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.billing import validate_consultation_billing_settings
from vetedge.services.registration_billing import validate_registration_settings


class VeterinarySettings(Document):
	def validate(self) -> None:
		if not self.get("enable_vetedge"):
			clear_fields(
				self,
				[
					"enable_registration_billing",
					"enable_consultations",
					"enable_consultation_billing",
					"allow_doctor_collect_payment",
					"consultation_requires_payment_before_treatment",
					"enable_vitals",
					"require_vitals_before_completion",
					"enable_appointments",
					"enable_owner_portal",
					"enable_guest_booking",
					"allow_owner_cancel_appointment",
					"allow_owner_reschedule_appointment",
					"enable_portal_payments",
					"enable_notifications",
					"enable_email_notifications",
					"enable_sms_notifications",
					"enable_whatsapp_notifications",
					"notification_backend_mode",
					"processedge_core_notifications_enabled",
					"notify_on_appointment_create",
					"notify_on_appointment_status_change",
					"notify_on_appointment_reminder",
					"notify_on_owner_portal_appointment_request",
					"notify_on_guest_registration_request",
					"notify_on_guest_registration_confirmed",
					"notify_on_guest_appointment_request",
					"notify_on_reschedule",
					"notify_on_cancellation",
					"appointment_reminder_hours",
					"vaccination_due_reminder_days",
					"payment_reminder_days",
					"enable_treatment_billing",
					"enable_dispensary_flow",
					"enforce_strict_expiry_control",
					"block_manual_expired_batch_override",
					"enable_vaccination",
					"enable_veterinary_hospitalisation",
					"enable_grooming",
					"enable_grooming_billing",
					"require_grooming_appointment",
					"allow_grooming_without_consultation",
					"vaccination_requires_payment_before_administration",
					"enable_boarding",
					"enable_demo_tools",
					"patient_branch_restriction_enabled",
					"enable_advanced_reports",
				],
			)
			set_if_field_exists(self, "portal_show_consultation_summary_only", 1)
			set_if_field_exists(self, "batch_selection_policy", "FEFO")

		if not self.get("enable_vitals"):
			set_if_field_exists(self, "require_vitals_before_completion", 0)

		if not self.get("enable_vaccination"):
			set_if_field_exists(self, "vaccination_requires_payment_before_administration", 0)

		if not self.get("enable_grooming"):
			set_if_field_exists(self, "enable_grooming_billing", 0)
			set_if_field_exists(self, "require_grooming_appointment", 0)
			set_if_field_exists(self, "allow_grooming_without_consultation", 1)

		if not self.get("enable_boarding"):
			set_if_field_exists(self, "default_boarding_billing_item", None)
			set_if_field_exists(self, "default_boarding_daily_rate", None)
			set_if_field_exists(self, "boarding_requires_payment_before_check_in", 0)

		if not self.get("enable_consultations"):
			set_if_field_exists(self, "enable_consultation_billing", 0)

		if not self.get("enable_consultation_billing"):
			set_if_field_exists(self, "allow_doctor_collect_payment", 0)
			set_if_field_exists(self, "consultation_requires_payment_before_treatment", 0)

		if not self.get("enable_notifications"):
			clear_fields(
				self,
				[
					"enable_email_notifications",
					"enable_sms_notifications",
					"enable_whatsapp_notifications",
					"notify_on_appointment_create",
					"notify_on_appointment_status_change",
					"notify_on_appointment_reminder",
					"notify_on_owner_portal_appointment_request",
					"notify_on_guest_registration_request",
					"notify_on_guest_registration_confirmed",
					"notify_on_guest_appointment_request",
					"notify_on_reschedule",
					"notify_on_cancellation",
					"notify_on_invoice_created",
					"notify_on_payment_received",
					"notify_on_accounts_action_required",
					"processedge_core_notifications_enabled",
				],
			)
			set_if_field_exists(self, "notification_channels", None)
			set_if_field_exists(self, "notification_backend_mode", "local")
			set_if_field_exists(self, "processedge_core_notification_endpoint", None)
			set_if_field_exists(self, "processedge_core_notification_api_key", None)

		if self.get("enable_notifications"):
			if self.meta.has_field("appointment_reminder_hours") and self.get("appointment_reminder_hours"):
				set_if_field_exists(self, "appointment_reminder_hours_before", self.get("appointment_reminder_hours"))
			elif self.meta.has_field("appointment_reminder_hours_before") and self.get("appointment_reminder_hours_before"):
				set_if_field_exists(self, "appointment_reminder_hours", self.get("appointment_reminder_hours_before"))

			if any(
				self.get(fieldname)
				for fieldname in ("enable_email_notifications", "enable_sms_notifications", "enable_whatsapp_notifications")
			):
				primary_channel = None
				if self.get("enable_email_notifications"):
					primary_channel = "Email"
				elif self.get("enable_sms_notifications"):
					primary_channel = "SMS"
				elif self.get("enable_whatsapp_notifications"):
					primary_channel = "WhatsApp"
				set_if_field_exists(self, "notification_channels", primary_channel)
			elif self.get("notification_channels"):
				set_if_field_exists(self, "enable_email_notifications", self.get("notification_channels") == "Email")
				set_if_field_exists(self, "enable_sms_notifications", self.get("notification_channels") == "SMS")
				set_if_field_exists(self, "enable_whatsapp_notifications", self.get("notification_channels") == "WhatsApp")

			if self.meta.has_field("notification_backend_mode") and not self.get("notification_backend_mode"):
				self.set("notification_backend_mode", "local")

		if not self.get("enable_dispensary_flow"):
			set_if_field_exists(self, "enforce_strict_expiry_control", 1)
			set_if_field_exists(self, "block_manual_expired_batch_override", 1)
			set_if_field_exists(self, "batch_selection_policy", "FEFO")

		if not self.get("enable_owner_portal"):
			clear_fields(
				self,
				[
					"allow_owner_cancel_appointment",
					"allow_owner_reschedule_appointment",
					"enable_portal_payments",
				],
			)
			set_if_field_exists(self, "portal_show_consultation_summary_only", 1)
		if self.meta.has_field("payment_backend_mode") and not self.get("payment_backend_mode"):
			self.set("payment_backend_mode", "stub")

		validate_registration_settings(self)
		validate_consultation_billing_settings(self)


def clear_fields(doc, fieldnames: list[str]) -> None:
	for fieldname in fieldnames:
		set_if_field_exists(doc, fieldname, 0)


def set_if_field_exists(doc, fieldname: str, value) -> None:
	if doc.meta.has_field(fieldname):
		doc.set(fieldname, value)
