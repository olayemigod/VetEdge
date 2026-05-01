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
					"notify_on_appointment_create",
					"notify_on_appointment_status_change",
					"notify_on_appointment_reminder",
					"notify_on_owner_portal_appointment_request",
					"notify_on_guest_registration_request",
					"notify_on_guest_registration_confirmed",
					"notify_on_guest_appointment_request",
					"notify_on_reschedule",
					"notify_on_cancellation",
					"enable_treatment_billing",
					"enable_dispensary_flow",
					"enforce_strict_expiry_control",
					"block_manual_expired_batch_override",
					"enable_vaccination",
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

		if not self.get("enable_consultations"):
			set_if_field_exists(self, "enable_consultation_billing", 0)

		if not self.get("enable_consultation_billing"):
			set_if_field_exists(self, "allow_doctor_collect_payment", 0)
			set_if_field_exists(self, "consultation_requires_payment_before_treatment", 0)

		if not self.get("enable_notifications"):
			clear_fields(
				self,
				[
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
				],
			)
			set_if_field_exists(self, "notification_channels", None)

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
